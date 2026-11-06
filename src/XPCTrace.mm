#import "XPCTrace.h"
#import "Common.h"
#import <objc/runtime.h>
#import <objc/message.h>
#include <dlfcn.h>
#include <atomic>
#include <mutex>
#include <vector>

// These hooks exist only in the disposable worker's address space. The exact
// client and connection objects are retained for that process's lifetime, so a
// late callback cannot observe a freed identity or a reused object address.
@interface CDXPCTraceConnection : NSObject
@property(nonatomic, strong) NSXPCConnection *connection;
@property(atomic, copy) NSDictionary *metadata;
@property(nonatomic, copy) void (^installedInterruption)(void);
@property(nonatomic, copy) void (^installedInvalidation)(void);
@property(nonatomic) BOOL complete;
@property(nonatomic) NSUInteger setupAttempts;
@property(nonatomic) BOOL protocolInventoried;
@end
@implementation CDXPCTraceConnection
@end

@interface CDXPCTraceClient : NSObject
@property(nonatomic, strong) id client;
@property(nonatomic, copy) NSString *profile;
@end
@implementation CDXPCTraceClient
@end

namespace {
struct Hook { Class cls; SEL selector; IMP original; IMP replacement; };
// Intentionally process-lifetime storage: C++ exit handlers must not destroy a
// lock/hook registry while NSXPC still has a callback queued on another thread.
std::recursive_mutex &traceMutex=*new std::recursive_mutex;
NSMutableDictionary<NSValue *, CDXPCTraceConnection *> *connections;
NSMutableDictionary<NSValue *, CDXPCTraceClient *> *clients;
std::vector<Hook> &hooks=*new std::vector<Hook>;
std::atomic<bool> cleanup{false};
NSUInteger errorCount=0, interruptionCount=0, invalidationCount=0, rejectedCount=0;
constexpr NSUInteger maxConnections=16;

NSValue *Identity(id object) { return [NSValue valueWithPointer:(__bridge const void *)object]; }
NSString *Bounded(NSString *value, NSUInteger limit=768) {
    if (![value isKindOfClass:NSString.class]) return @"";
    if (value.length<=limit) return value;
    // Do not split a UTF-16 surrogate pair at the bound.
    if (limit && CFStringIsSurrogateHighCharacter([value characterAtIndex:limit-1])) --limit;
    return [[value substringToIndex:limit] stringByAppendingString:@"…"];
}
void Emit(NSString *event, NSDictionary *fields) {
    // Diagnostics must not prevent a native error/reply/lifecycle callback.
    @try {
        NSData *encoded=[NSJSONSerialization dataWithJSONObject:fields options:0 error:NULL];
        if (!encoded || encoded.length>12*1024) {
            NSMutableDictionary *small=[@{@"details_truncated":@YES,@"reason":@"trace_event_size_limit"} mutableCopy];
            if (fields[@"connection_id"]) small[@"connection_id"]=Bounded(fields[@"connection_id"],64);
            if ([fields[@"error"] isKindOfClass:NSDictionary.class]) {
                NSDictionary *error=fields[@"error"];
                small[@"error"]=@{@"domain":Bounded(error[@"domain"],96),@"code":error[@"code"]?:@0};
            }
            CDEmit(event,small);
        } else CDEmit(event,fields);
    } @catch (__unused NSException *exception) {}
}
NSDictionary *ErrorFacts(NSError *error, NSUInteger depth=0) {
    if (![error isKindOfClass:NSError.class]) return @{@"available":@NO};
    NSMutableDictionary *facts=[NSMutableDictionary dictionary];
    @try {
        facts[@"domain"]=Bounded(error.domain,256); facts[@"code"]=@(error.code);
        facts[@"description"]=Bounded(error.localizedDescription);
        NSString *reason=error.localizedFailureReason;
        if (reason.length) facts[@"failure_reason"]=Bounded(reason);
        NSDictionary *userInfo=error.userInfo;
        if ([userInfo[@"NSDebugDescription"] isKindOfClass:NSString.class])
            facts[@"debug_description"]=Bounded(userInfo[@"NSDebugDescription"]);
        NSError *underlying=userInfo[NSUnderlyingErrorKey];
        if ([underlying isKindOfClass:NSError.class]) {
            if (depth<2) facts[@"underlying"]=ErrorFacts(underlying,depth+1);
            else facts[@"underlying_truncated"]=@YES;
        }
    } @catch (NSException *exception) { facts[@"inspection_exception"]=Bounded(exception.name,128); }
    return facts;
}
NSDictionary *SmallErrorFacts(NSDictionary *facts) {
    NSMutableDictionary *small=[@{@"domain":Bounded(facts[@"domain"],96),@"code":facts[@"code"]?:@0,
        @"description":Bounded(facts[@"description"],128),@"details_truncated":@YES} mutableCopy];
    if (facts[@"debug_description"]) small[@"debug_description"]=Bounded(facts[@"debug_description"],96);
    if ([facts[@"underlying"] isKindOfClass:NSDictionary.class]) small[@"underlying"]=SmallErrorFacts(facts[@"underlying"]);
    if (facts[@"underlying_truncated"]) small[@"underlying_truncated"]=@YES;
    return small;
}
CDXPCTraceConnection *ConnectionState(id connection) {
    std::lock_guard<std::recursive_mutex> lock(traceMutex);
    return connections[Identity(connection)];
}
CDXPCTraceClient *ClientState(id client) {
    std::lock_guard<std::recursive_mutex> lock(traceMutex);
    return clients[Identity(client)];
}
void ConnectionEvent(NSString *event, CDXPCTraceConnection *state, NSDictionary *extra) {
    NSDictionary *snapshot;
    { std::lock_guard<std::recursive_mutex> lock(traceMutex); snapshot=state.metadata; }
    NSMutableDictionary *facts=[snapshot mutableCopy];
    [facts addEntriesFromDictionary:extra]; facts[@"cleanup"]=@(cleanup.load());
    Emit(event,facts);
}
void ProxyError(CDXPCTraceConnection *state, NSString *variant, NSError *error) {
    { std::lock_guard<std::recursive_mutex> lock(traceMutex); ++errorCount; }
    ConnectionEvent(@"xpc_proxy_error",state,@{@"variant":variant,@"error":CDXPCTraceError(error)});
}
IMP Original(IMP implementation) {
    for (const Hook &hook : hooks) if (hook.replacement==implementation) return hook.original;
    return implementation;
}
BOOL AppleOwner(IMP implementation) {
    Dl_info info={}; if (!dladdr((const void *)implementation,&info) || !info.dli_fname) return NO;
    NSString *path=@(info.dli_fname);
    return [path hasPrefix:@"/System/Library/"] || [path hasPrefix:@"/usr/lib/"];
}
BOOL ClientOwner(IMP implementation) {
    Dl_info info={}; if (!dladdr((const void *)implementation,&info) || !info.dli_fname) return NO;
    if (AppleOwner(implementation) && strstr(info.dli_fname,"/CarKit.framework/")) return YES;
#if CD_HOST_TEST
    // The host fixture lives in the test executable; never enabled in the DEB.
    Dl_info own={}; return dladdr((const void *)&CDXPCTraceRegisterClient,&own) &&
        own.dli_fname && strcmp(info.dli_fname,own.dli_fname)==0;
#else
    return NO;
#endif
}
BOOL Signature(Method method, const char *result, NSArray<NSString *> *arguments) {
    if (!method) return NO;
    NSMethodSignature *signature=[NSMethodSignature signatureWithObjCTypes:method_getTypeEncoding(method)];
    if (!signature || strcmp(signature.methodReturnType,result) || signature.numberOfArguments!=arguments.count+2) return NO;
    for (NSUInteger index=0;index<arguments.count;++index)
        if (strcmp([signature getArgumentTypeAtIndex:index+2],arguments[index].UTF8String)) return NO;
    return YES;
}
BOOL AlreadyHooked(IMP implementation) {
    for (const Hook &hook : hooks) if (hook.replacement==implementation) return YES;
    return NO;
}
void Install(Class cls, SEL selector, Method method, IMP original, IMP replacement) {
    // Adding a local method avoids changing a superclass's method accidentally.
    if (!class_addMethod(cls,selector,replacement,method_getTypeEncoding(method)))
        class_replaceMethod(cls,selector,replacement,method_getTypeEncoding(method));
    hooks.push_back({cls,selector,original,replacement});
}

BOOL HookErrorProxy(Class cls, SEL selector, NSString *variant) {
    Method method=class_getInstanceMethod(cls,selector);
    if (!Signature(method,"@",@[@"@?"])) return NO;
    IMP implementation=method_getImplementation(method);
    if (AlreadyHooked(implementation)) return YES;
    if (!AppleOwner(implementation)) return NO;
    typedef id (*Call)(id,SEL,void (^)(NSError *)); Call original=(Call)implementation;
    IMP replacement=imp_implementationWithBlock(^id(id object,void (^handler)(NSError *)) {
        CDXPCTraceConnection *state=ConnectionState(object);
        if (!state) return original(object,selector,handler);
        void (^forward)(NSError *)=[handler copy];
        ConnectionEvent(@"xpc_proxy_requested",state,@{@"variant":variant});
        return original(object,selector,^(NSError *error) {
            ProxyError(state,variant,error);
            if (forward) forward(error);
        });
    });
    Install(cls,selector,method,implementation,replacement); return YES;
}
BOOL HookPlainProxy(Class cls) {
    SEL selector=@selector(remoteObjectProxy), errorSelector=@selector(remoteObjectProxyWithErrorHandler:);
    Method method=class_getInstanceMethod(cls,selector), errorMethod=class_getInstanceMethod(cls,errorSelector);
    if (!Signature(method,"@",@[]) || !Signature(errorMethod,"@",@[@"@?"])) return NO;
    IMP implementation=method_getImplementation(method);
    if (AlreadyHooked(implementation)) return YES;
    IMP errorImplementation=Original(method_getImplementation(errorMethod));
    if (!AppleOwner(implementation) || !AppleOwner(errorImplementation)) return NO;
    typedef id (*PlainCall)(id,SEL); typedef id (*ErrorCall)(id,SEL,void (^)(NSError *));
    PlainCall original=(PlainCall)implementation; ErrorCall withError=(ErrorCall)errorImplementation;
    IMP replacement=imp_implementationWithBlock(^id(id object) {
        CDXPCTraceConnection *state=ConnectionState(object);
        if (!state) return original(object,selector);
        // Keep the asynchronous variant asynchronous. This adds an error sink,
        // not a second request, synchronous wait, or different remote method.
        ConnectionEvent(@"xpc_proxy_requested",state,@{@"variant":@"plain_async"});
        return withError(object,errorSelector,^(NSError *error) { ProxyError(state,@"plain_async",error); });
    });
    Install(cls,selector,method,implementation,replacement); return YES;
}
BOOL HookHandlerSetter(Class cls, BOOL invalidation) {
    SEL selector=invalidation?@selector(setInvalidationHandler:):@selector(setInterruptionHandler:);
    Method method=class_getInstanceMethod(cls,selector);
    if (!Signature(method,"v",@[@"@?"])) return NO;
    IMP implementation=method_getImplementation(method);
    if (AlreadyHooked(implementation)) return YES;
    if (!AppleOwner(implementation)) return NO;
    typedef void (*Call)(id,SEL,void (^)(void)); Call original=(Call)implementation;
    IMP replacement=imp_implementationWithBlock(^(id object,void (^handler)(void)) {
        CDXPCTraceConnection *state=ConnectionState(object);
        if (!state) { original(object,selector,handler); return; }
        BOOL alreadyWrapped=NO;
        {
            std::lock_guard<std::recursive_mutex> lock(traceMutex);
            id installed=invalidation?state.installedInvalidation:state.installedInterruption;
            alreadyWrapped=handler && handler==installed;
        }
        if (alreadyWrapped) { original(object,selector,handler); return; }
        void (^forward)(void)=[handler copy];
        void (^wrapped)(void)=^{
            {
                std::lock_guard<std::recursive_mutex> lock(traceMutex);
                if (invalidation) ++invalidationCount; else ++interruptionCount;
            }
            // Only immutable pre-captured metadata is used here. Never query,
            // resume, invalidate or send a message on an invalidated connection.
            ConnectionEvent(invalidation?@"xpc_connection_invalidated":@"xpc_connection_interrupted",state,@{});
            if (forward) forward();
        };
        {
            std::lock_guard<std::recursive_mutex> lock(traceMutex);
            if (invalidation) state.installedInvalidation=wrapped; else state.installedInterruption=wrapped;
        }
        original(object,selector,wrapped);
    });
    Install(cls,selector,method,implementation,replacement); return YES;
}

NSString *RuntimeText(const char *text, size_t limit, BOOL *truncated) {
    if (!text) { *truncated=NO; return @""; }
    size_t size=strnlen(text,limit+1); *truncated=size>limit;
    NSString *value=[[NSString alloc] initWithBytes:text length:MIN(size,limit) encoding:NSUTF8StringEncoding];
    return value?:@"<non-UTF8 metadata>";
}
void ProtocolInventory(Protocol *remote, CDXPCTraceConnection *state) {
    // The SPI only reads compiler-emitted extended encodings. It is never used
    // to invoke an unknown remote method or to guess a completion block ABI.
    typedef const char *(*ExtendedEncoding)(Protocol *,SEL,BOOL,BOOL);
    void *symbol=dlsym(RTLD_DEFAULT,"_protocol_getMethodTypeEncoding");
    Dl_info owner={}; BOOL trusted=symbol && dladdr(symbol,&owner) && owner.dli_fname &&
        strcmp(owner.dli_fname,"/usr/lib/libobjc.A.dylib")==0;
    ExtendedEncoding extended=trusted?(ExtendedEncoding)symbol:nullptr;
    NSString *identifier=state.metadata[@"connection_id"];
    if (!remote) {
        Emit(@"xpc_protocol_inventory",@{@"connection_id":identifier,@"available":@NO,@"reason":@"remote_interface_protocol_unavailable",
            @"extended_encoding_provider_available":@(extended!=nullptr),@"method_count":@0}); return;
    }
    constexpr NSUInteger methodLimit=40,protocolLimit=8,byteLimit=32*1024;
    NSMutableArray<Protocol *> *pending=[NSMutableArray arrayWithObject:remote];
    NSMutableSet<NSValue *> *visited=[NSMutableSet set];
    NSUInteger methods=0,bytes=0,extendedCount=0; BOOL truncated=NO,budgetExhausted=NO;
    while (pending.count && visited.count<protocolLimit && methods<methodLimit && !budgetExhausted) {
        Protocol *protocol=pending.firstObject; [pending removeObjectAtIndex:0];
        NSValue *identity=Identity(protocol); if ([visited containsObject:identity]) continue; [visited addObject:identity];
        for (BOOL required : {YES,NO}) for (BOOL instance : {YES,NO}) {
            unsigned count=0;
            struct objc_method_description *list=protocol_copyMethodDescriptionList(protocol,required,instance,&count);
            for (unsigned index=0;index<count;++index) {
                if (methods>=methodLimit || budgetExhausted) { truncated=YES; break; }
                if (!list[index].name) continue;
                BOOL ordinaryTruncated=NO,extendedTruncated=NO,selectorTruncated=NO;
                const char *extra=extended?extended(protocol,list[index].name,required,instance):nullptr;
                NSString *ordinaryText=RuntimeText(list[index].types,512,&ordinaryTruncated);
                NSString *extendedText=RuntimeText(extra,1024,&extendedTruncated);
                NSDictionary *row=@{@"connection_id":identifier,@"protocol":Bounded(NSStringFromProtocol(protocol),128),
                    @"selector":RuntimeText(sel_getName(list[index].name),256,&selectorTruncated),@"required":@(required),@"instance":@(instance),
                    @"encoding":ordinaryText,@"encoding_available":@(list[index].types!=nullptr),@"encoding_truncated":@(ordinaryTruncated),
                    @"extended_encoding":extendedText,@"extended_encoding_available":@(extra!=nullptr),
                    @"extended_encoding_truncated":@(extendedTruncated),@"selector_truncated":@(selectorTruncated)};
                NSUInteger size=[NSJSONSerialization dataWithJSONObject:row options:0 error:NULL].length;
                if (size>byteLimit-bytes) { truncated=YES; budgetExhausted=YES; break; }
                bytes+=size; ++methods; if (extra) ++extendedCount; Emit(@"xpc_protocol_method",row);
            }
            free(list);
        }
        unsigned inheritedCount=0; Protocol *__unsafe_unretained *inherited=protocol_copyProtocolList(protocol,&inheritedCount);
        for (unsigned index=0;index<inheritedCount;++index) {
            if (pending.count+visited.count>=protocolLimit) { truncated=YES; break; }
            if (![visited containsObject:Identity(inherited[index])]) [pending addObject:inherited[index]];
        }
        free(inherited);
    }
    if (pending.count) truncated=YES;
    Emit(@"xpc_protocol_inventory",@{@"connection_id":identifier,@"available":@YES,@"protocol_count":@(visited.count),
        @"method_count":@(methods),@"metadata_bytes":@(bytes),@"method_limit":@(methodLimit),@"byte_limit":@(byteLimit),
        @"truncated":@(truncated),@"extended_encoding_provider_available":@(extended!=nullptr),
        @"extended_encoding_provider_owner":owner.dli_fname?Bounded(@(owner.dli_fname),256):@"",
        @"methods_with_extended_encoding":@(extendedCount),@"remote_methods_invoked":@NO});
}

void RegisterConnection(id value, CDXPCTraceClient *client) {
    if (!value) { Emit(@"xpc_connection_unavailable",@{@"profile":client.profile,@"reason":@"getter_returned_nil"}); return; }
    if (![value isKindOfClass:NSXPCConnection.class]) {
        Emit(@"xpc_connection_unavailable",@{@"profile":client.profile,@"reason":@"getter_returned_non_NSXPCConnection",@"class":NSStringFromClass(object_getClass(value))}); return;
    }
    std::lock_guard<std::recursive_mutex> lock(traceMutex);
    CDXPCTraceConnection *state=connections[Identity(value)];
    if (state && (state.complete || state.setupAttempts>=3)) return;
    if (!state && connections.count>=maxConnections) {
        ++rejectedCount; Emit(@"xpc_connection_unavailable",@{@"reason":@"observation_connection_limit"}); return;
    }
    NSXPCConnection *connection=value; Class cls=object_getClass(connection);
    NSString *identifier=state.metadata[@"connection_id"]?:[NSString stringWithFormat:@"xpc-%lu",(unsigned long)connections.count+1];
    NSMutableDictionary *metadata=[@{@"connection_id":identifier,
        @"profile":client.profile,@"class":Bounded(NSStringFromClass(cls),96)} mutableCopy];
    Protocol *remote=nil;
    @try {
        metadata[@"service_name"]=Bounded(connection.serviceName?:@"",192);
        metadata[@"listener_endpoint_present"]=@(connection.endpoint!=nil);
        remote=connection.remoteObjectInterface.protocol;
        Protocol *exported=connection.exportedInterface.protocol;
        metadata[@"remote_protocol"]=remote?Bounded(NSStringFromProtocol(remote),96):@"";
        metadata[@"exported_protocol"]=exported?Bounded(NSStringFromProtocol(exported),96):@"";
    } @catch (NSException *exception) { metadata[@"metadata_exception"]=Bounded(exception.name,128); }
    BOOL async=HookErrorProxy(cls,@selector(remoteObjectProxyWithErrorHandler:),@"async");
    BOOL sync=HookErrorProxy(cls,@selector(synchronousRemoteObjectProxyWithErrorHandler:),@"sync");
    BOOL plain=HookPlainProxy(cls);
    BOOL interruption=HookHandlerSetter(cls,NO), invalidation=HookHandlerSetter(cls,YES);
    metadata[@"coverage"]=@{@"async_error_proxy":@(async),@"sync_error_proxy":@(sync),@"plain_proxy":@(plain),
        @"interruption":@NO,@"invalidation":@NO};
    metadata[@"setup_in_progress"]=@YES;
    if (!state) state=[CDXPCTraceConnection new]; state.connection=connection;
    state.metadata=metadata; state.complete=NO; ++state.setupAttempts;
    connections[Identity(connection)]=state;
    // Chain pre-existing handlers and also intercept subsequent replacements.
    // Each path is independent: one throwing getter/setter must not hide the
    // other lifecycle event or claim full coverage before installation succeeds.
    BOOL interruptionReady=NO,invalidationReady=NO;
    if (interruption) {
        @try { connection.interruptionHandler=connection.interruptionHandler; interruptionReady=YES; }
        @catch (NSException *exception) {
            ConnectionEvent(@"xpc_handler_setup_failed",state,@{@"handler":@"interruption",@"exception":Bounded(exception.name,128)});
        }
    }
    if (invalidation) {
        @try { connection.invalidationHandler=connection.invalidationHandler; invalidationReady=YES; }
        @catch (NSException *exception) {
            ConnectionEvent(@"xpc_handler_setup_failed",state,@{@"handler":@"invalidation",@"exception":Bounded(exception.name,128)});
        }
    }
    metadata[@"coverage"]=@{@"async_error_proxy":@(async),@"sync_error_proxy":@(sync),@"plain_proxy":@(plain),
        @"interruption":@(interruptionReady),@"invalidation":@(invalidationReady)};
    metadata[@"setup_attempt"]=@(state.setupAttempts);
    metadata[@"setup_in_progress"]=@NO;
    state.metadata=metadata; state.complete=async&&sync&&plain&&interruptionReady&&invalidationReady;
    ConnectionEvent(@"xpc_connection_observed",state,@{});
    if (!state.protocolInventoried) {
        state.protocolInventoried=YES;
        @try { ProtocolInventory(remote,state); }
        @catch (NSException *exception) {
            Emit(@"xpc_protocol_inventory",@{@"connection_id":identifier,@"available":@NO,
                @"reason":@"metadata_exception",@"exception":Bounded(exception.name,128)});
        }
    }
}
BOOL HookClientGetter(Class cls) {
    SEL selector=NSSelectorFromString(@"serviceConnection"); Method method=class_getInstanceMethod(cls,selector);
    if (!Signature(method,"@",@[])) return NO;
    IMP implementation=method_getImplementation(method);
    if (AlreadyHooked(implementation)) return YES;
    if (!ClientOwner(implementation)) return NO;
    typedef id (*Call)(id,SEL); Call original=(Call)implementation;
    IMP replacement=imp_implementationWithBlock(^id(id object) {
        id connection=original(object,selector);
        CDXPCTraceClient *client=ClientState(object);
        if (client) {
            @try { RegisterConnection(connection,client); }
            @catch (NSException *exception) {
                Emit(@"xpc_connection_unavailable",@{@"profile":client.profile,@"reason":@"observer_exception",
                    @"exception":Bounded(exception.name,128)});
            }
        }
        return connection;
    });
    Install(cls,selector,method,implementation,replacement); return YES;
}
} // namespace

BOOL CDXPCTraceRegisterClient(id client, NSString *profile) {
    if (!client) return NO;
    NSString *className=NSStringFromClass(object_getClass(client));
    BOOL expected=[className isEqual:@"CARSessionRequestClient"];
#if CD_HOST_TEST
    expected=expected || [className isEqual:@"CDXPCClientFixture"];
#endif
    if (!expected) { Emit(@"xpc_trace_unavailable",@{@"reason":@"unexpected_client_class",@"class":className}); return NO; }
    {
        std::lock_guard<std::recursive_mutex> lock(traceMutex);
        if (!clients) clients=[NSMutableDictionary dictionary];
        if (!connections) connections=[NSMutableDictionary dictionary];
        if (clients[Identity(client)]) return YES;
        if (!HookClientGetter(object_getClass(client))) {
            Emit(@"xpc_trace_unavailable",@{@"reason":@"client_getter_ABI_or_owner_guard_failed"}); return NO;
        }
        CDXPCTraceClient *state=[CDXPCTraceClient new]; state.client=client; state.profile=Bounded(profile?:@"",96);
        clients[Identity(client)]=state;
    }
    // Prime observation before the request, including clients that subsequently
    // access the connection ivar directly. This calls a getter, never a start,
    // cancel, resume or remote method. It may create the client's lazy connection.
    @try {
        ((id(*)(id,SEL))objc_msgSend)(client,NSSelectorFromString(@"serviceConnection"));
    } @catch (NSException *exception) {
        Emit(@"xpc_trace_unavailable",@{@"reason":@"client_getter_exception",@"exception":Bounded(exception.name,128)}); return NO;
    }
    Emit(@"xpc_trace_registered",@{@"client_class":className,@"scope":@"owned_worker_connections_only",@"getter_primed":@YES});
    return YES;
}

void CDXPCTraceBeginCleanup(void) { cleanup.store(true); }

NSDictionary *CDXPCTraceError(NSError *error) {
    NSDictionary *facts=ErrorFacts(error);
    NSData *encoded=[NSJSONSerialization dataWithJSONObject:facts options:0 error:NULL];
    return encoded && encoded.length<=8*1024 ? facts : SmallErrorFacts(facts);
}

NSDictionary *CDXPCTraceSummary(void) {
    std::lock_guard<std::recursive_mutex> lock(traceMutex); NSUInteger complete=0;
    for (CDXPCTraceConnection *state in connections.allValues) if (state.complete) ++complete;
    return @{@"scope":@"owned_worker_connections_only",@"clients":@(clients.count),@"connections":@(connections.count),
        @"fully_instrumented_connections":@(complete),@"proxy_errors":@(errorCount),@"interruptions":@(interruptionCount),
        @"invalidations":@(invalidationCount),@"rejected_connections":@(rejectedCount),@"cleanup":@(cleanup.load()),
        @"daemon_logs_observed":@NO,@"connection_limit":@(maxConnections)};
}
