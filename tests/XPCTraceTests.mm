#import "XPCTrace.h"
#import <objc/runtime.h>
#include <atomic>
#include <functional>
#include <mutex>
#include <unistd.h>

// Transport integration fixtures. This server uses real anonymous NSXPC
// connections; no proxy, connection, reply, or failure is mocked.
@protocol CDTraceInherited
@optional
- (void)optionalFlag:(BOOL)flag completion:(void (^)(BOOL, NSError *))completion;
@end
@protocol CDTraceEcho <CDTraceInherited>
- (void)echo:(NSString *)text reply:(void (^)(NSString *))reply;
- (void)ping;
@end
#define CD_TEN_METHODS(prefix) \
    - (void)prefix##0; - (void)prefix##1; - (void)prefix##2; - (void)prefix##3; - (void)prefix##4; \
    - (void)prefix##5; - (void)prefix##6; - (void)prefix##7; - (void)prefix##8; - (void)prefix##9;
@protocol CDTraceLarge
CD_TEN_METHODS(method0) CD_TEN_METHODS(method1) CD_TEN_METHODS(method2) CD_TEN_METHODS(method3) CD_TEN_METHODS(method4)
CD_TEN_METHODS(method5) CD_TEN_METHODS(method6) CD_TEN_METHODS(method7) CD_TEN_METHODS(method8) CD_TEN_METHODS(method9)
@end
#undef CD_TEN_METHODS
@interface CDTraceServer : NSObject <NSXPCListenerDelegate, CDTraceEcho>
@property(nonatomic, strong) NSMutableArray<NSXPCConnection *> *accepted;
@end
@implementation CDTraceServer
- (instancetype)init { if ((self=[super init])) _accepted=[NSMutableArray array]; return self; }
- (BOOL)listener:(NSXPCListener *)listener shouldAcceptNewConnection:(NSXPCConnection *)connection {
    (void)listener;
    connection.exportedInterface=[NSXPCInterface interfaceWithProtocol:@protocol(CDTraceEcho)];
    connection.exportedObject=self;
    @synchronized(self) { [_accepted addObject:connection]; }
    [connection resume]; return YES;
}
- (void)echo:(NSString *)text reply:(void (^)(NSString *))reply { reply(text); }
- (void)ping {}
- (void)disconnect {
    NSArray *connections; @synchronized(self) { connections=[_accepted copy]; }
    for (NSXPCConnection *connection in connections) [connection invalidate];
}
@end

@interface CDXPCClientFixture : NSObject
@property(nonatomic, strong) NSXPCConnection *serviceConnection;
@end
@implementation CDXPCClientFixture
@end

@interface CDThrowingConnection : NSXPCConnection
@property(atomic) BOOL failInvalidationRead;
@end
@implementation CDThrowingConnection
- (void (^)(void))invalidationHandler {
    if (self.failInvalidationRead) @throw [NSException exceptionWithName:@"TestGetterFailure" reason:nil userInfo:nil];
    return [super invalidationHandler];
}
@end

static std::mutex outputMutex;
static NSMutableArray<NSDictionary *> *rows;
void CDEmit(NSString *event, NSDictionary *fields) {
    std::lock_guard<std::mutex> lock(outputMutex);
    NSMutableDictionary *row=[fields mutableCopy]; row[@"event"]=event;
    [rows addObject:row];
    NSData *data=[NSJSONSerialization dataWithJSONObject:row options:0 error:NULL];
    fwrite(data.bytes,1,data.length,stdout); fputc('\n',stdout); fflush(stdout);
}
static NSArray<NSDictionary *> *Events(NSString *name) {
    std::lock_guard<std::mutex> lock(outputMutex);
    NSMutableArray *found=[NSMutableArray array];
    for (NSDictionary *row in rows) if ([row[@"event"] isEqual:name]) [found addObject:row];
    return found;
}
static bool Wait(const std::function<bool(void)> &predicate, double seconds=4) {
    NSDate *deadline=[NSDate dateWithTimeIntervalSinceNow:seconds];
    while (!predicate() && [deadline timeIntervalSinceNow]>0) usleep(1000);
    return predicate();
}
static void Check(bool valid, const char *message) {
    if (!valid) { fprintf(stderr,"FAIL: %s\n",message); exit(1); }
}
static NSXPCConnection *Missing(void) {
    NSXPCConnection *connection=[[NSXPCConnection alloc] initWithMachServiceName:
        [@"com.cfluid.cardash.trace.nonexistent." stringByAppendingString:NSUUID.UUID.UUIDString] options:0];
    connection.remoteObjectInterface=[NSXPCInterface interfaceWithProtocol:@protocol(CDTraceEcho)];
    return connection;
}
static CDXPCClientFixture *Client(NSXPCConnection *connection) {
    CDXPCClientFixture *client=[CDXPCClientFixture new]; client.serviceConnection=connection;
    return client;
}

#if CD_XPC_TRACE_BASELINE
// Deliberately inert baseline, compiled only to demonstrate that the actual
// missing-service transport error was invisible before adding the observer.
BOOL CDXPCTraceRegisterClient(id client, NSString *profile) { (void)client; (void)profile; return YES; }
void CDXPCTraceBeginCleanup(void) {}
NSDictionary *CDXPCTraceSummary(void) { return @{}; }
NSDictionary *CDXPCTraceError(NSError *error) { (void)error; return @{}; }
#endif

static void Failure(NSString *mode) {
    NSXPCConnection *connection=Missing(); CDXPCClientFixture *client=Client(connection);
    std::atomic<int> errors{0}, invalidations{0}, replies{0};
    __block NSError *originalError=nil;
    auto *errorsPtr=&errors, *invalidationsPtr=&invalidations, *repliesPtr=&replies;
    connection.invalidationHandler=^{ invalidationsPtr->fetch_add(1); };
    Check(CDXPCTraceRegisterClient(client,mode),"could not register owned client");
    [connection resume];
    if ([mode isEqual:@"missing-oneway"]) {
        [(id<CDTraceEcho>)[client.serviceConnection remoteObjectProxy] ping];
    } else if ([mode isEqual:@"missing-plain"]) {
        [(id<CDTraceEcho>)[client.serviceConnection remoteObjectProxy] echo:@"plain" reply:^(NSString *text) {
            (void)text; repliesPtr->fetch_add(1);
        }];
    } else {
        void (^error)(NSError *)=^(NSError *value) { originalError=value; errorsPtr->fetch_add(1); };
        id<CDTraceEcho> proxy=[mode isEqual:@"missing-sync"] ?
            [client.serviceConnection synchronousRemoteObjectProxyWithErrorHandler:error] :
            [client.serviceConnection remoteObjectProxyWithErrorHandler:error];
        [proxy echo:@"not delivered" reply:^(NSString *value) { (void)value; repliesPtr->fetch_add(1); }];
        if ([mode isEqual:@"missing-sync"]) Check(errors.load()==1,"synchronous error was deferred");
        Check(Wait([&] { return errors.load()==1; }),"original error callback was lost");
        Check(originalError!=nil && replies.load()==0,"failure incorrectly produced a reply");
    }
    if (![mode isEqual:@"missing-oneway"]) {
        Check(Wait([] { return Events(@"xpc_proxy_error").count==1; }),"missing-service error not captured exactly once");
        NSDictionary *event=Events(@"xpc_proxy_error").firstObject;
        Check([event[@"error"][@"domain"] isEqual:NSCocoaErrorDomain],"NSError domain missing");
        if (originalError) Check([event[@"error"][@"code"] integerValue]==originalError.code,"original NSError changed");
    }
    Check(Wait([&] { return invalidations.load()==1; }),"original invalidation handler was lost");
    Check(Events(@"xpc_connection_invalidated").count==1,"invalidation not recorded exactly once");
    [connection invalidate];
}

static void ErrorBounds(void) {
    NSString *longText=[@"\x01\x02🙂" stringByPaddingToLength:20000 withString:@"\x01\x02🙂" startingAtIndex:0];
    NSError *error=nil;
    for (int depth=0;depth<6;++depth) {
        NSMutableDictionary *user=[@{NSLocalizedDescriptionKey:longText,NSLocalizedFailureReasonErrorKey:longText,@"NSDebugDescription":longText} mutableCopy];
        if (error) user[NSUnderlyingErrorKey]=error;
        error=[NSError errorWithDomain:longText code:91 userInfo:user];
    }
    NSDictionary *facts=CDXPCTraceError(error);
    NSData *encoded=[NSJSONSerialization dataWithJSONObject:facts options:0 error:NULL];
    Check(encoded!=nil && encoded.length<=8192,"error exceeds report line budget or has split Unicode");
    Check([facts[@"code"] integerValue]==91,"bounded error lost its code");
    Check(facts[@"underlying"][@"underlying"]!=nil,"bounded error lost its first two causes");
    Check(facts[@"underlying"][@"underlying"][@"underlying"]==nil,"underlying error chain is unbounded");
    Check([facts[@"underlying"][@"underlying"][@"underlying_truncated"] boolValue],"truncation not disclosed");
}

static void GuardedRegistration(void) {
    Check(!CDXPCTraceRegisterClient([NSObject new],@"not a client"),"unexpected class accepted");
    Check([CDXPCTraceSummary()[@"clients"] unsignedIntegerValue]==0,"unaccepted client was retained");
    NSObject *notConnection=[NSObject new];
    CDXPCClientFixture *client=Client((NSXPCConnection *)notConnection);
    Check(CDXPCTraceRegisterClient(client,@"wrong return type"),"valid fixture getter was not observed");
    Check(client.serviceConnection==(id)notConnection,"observer changed the getter result");
    Check([CDXPCTraceSummary()[@"connections"] unsignedIntegerValue]==0,"non-NSXPC object was instrumented");
    Check(Events(@"xpc_connection_unavailable").count>0,"non-NSXPC coverage gap was hidden");
}

static void ForeignGetterOwner(void) {
    CDXPCClientFixture *client=Client(Missing());
    Method getter=class_getInstanceMethod(CDXPCClientFixture.class,@selector(serviceConnection));
    NSXPCConnection *connection=client.serviceConnection;
    // A foreign trampoline is not from the expected framework/test executable.
    IMP foreign=imp_implementationWithBlock(^id(__unused id object) { return connection; });
    class_replaceMethod(CDXPCClientFixture.class,@selector(serviceConnection),foreign,method_getTypeEncoding(getter));
    Check(!CDXPCTraceRegisterClient(client,@"foreign owner"),"foreign getter implementation was accepted");
    Check(client.serviceConnection==connection,"rejected getter was changed");
    Check([CDXPCTraceSummary()[@"connections"] unsignedIntegerValue]==0,"foreign-owned getter was instrumented");
    [connection invalidate];
}

static void HandlerSetupFailure(void) {
    CDThrowingConnection *connection=[[CDThrowingConnection alloc] initWithMachServiceName:
        [@"com.cfluid.cardash.trace.nonexistent." stringByAppendingString:NSUUID.UUID.UUIDString] options:0];
    connection.remoteObjectInterface=[NSXPCInterface interfaceWithProtocol:@protocol(CDTraceEcho)];
    connection.failInvalidationRead=YES;
    std::atomic<int> invalidations{0}; auto *invalidationsPtr=&invalidations;
    connection.invalidationHandler=^{ invalidationsPtr->fetch_add(1); };
    CDXPCClientFixture *client=Client(connection);
    Check(CDXPCTraceRegisterClient(client,@"throwing handler getter"),"observer changed a valid service getter");
    Check([CDXPCTraceSummary()[@"fully_instrumented_connections"] unsignedIntegerValue]==0,
        "handler setup exception was falsely reported as full coverage");
    Check(Events(@"xpc_handler_setup_failed").count==1,"handler setup exception was not reported");
    connection.failInvalidationRead=NO;
    Check(client.serviceConnection==connection,"retry changed the native getter return");
    Check([CDXPCTraceSummary()[@"fully_instrumented_connections"] unsignedIntegerValue]==1,
        "recoverable handler setup was never retried");
    [connection resume]; [connection invalidate];
    Check(Wait([&] { return invalidations.load()==1; }),"retry lost or duplicated the original lifecycle handler");
    Check(Events(@"xpc_connection_invalidated").count==1,"retry duplicated lifecycle capture");
}

static void ProtocolMetadata(void) {
    NSXPCConnection *connection=Missing(); CDXPCClientFixture *client=Client(connection);
    Check(CDXPCTraceRegisterClient(client,@"protocol inventory"),"could not register protocol fixture");
    NSArray *methods=Events(@"xpc_protocol_method");
    NSDictionary *echo=nil,*inherited=nil;
    for (NSDictionary *method in methods) {
        if ([method[@"selector"] isEqual:@"echo:reply:"]) echo=method;
        if ([method[@"selector"] isEqual:@"optionalFlag:completion:"]) inherited=method;
    }
    Check(echo!=nil && [echo[@"encoding"] containsString:@"@?"],"remote method block encoding missing");
    Check([echo[@"protocol"] isEqual:@"CDTraceEcho"] && [echo[@"required"] boolValue],"remote method provenance missing");
    Check(inherited!=nil && ![inherited[@"required"] boolValue],"inherited optional method metadata missing");
    Check([inherited[@"encoding"] containsString:@(@encode(BOOL))],"native BOOL argument encoding missing");
    NSDictionary *summary=Events(@"xpc_protocol_inventory").lastObject;
    Check([summary[@"available"] boolValue] && [summary[@"method_count"] unsignedIntegerValue]==methods.count,
        "protocol inventory coverage is missing");
    Check(summary[@"extended_encoding_provider_available"]!=nil,"optional extended ABI source availability not disclosed");
    // Inventory itself must not generate a remote proxy or send a method.
    Check(Events(@"xpc_proxy_requested").count==0,"metadata inventory sent a remote probe");
    [connection invalidate];
}

static void ProtocolBoundsAndUnavailable(void) {
    NSXPCConnection *connection=Missing(); connection.remoteObjectInterface=[NSXPCInterface interfaceWithProtocol:@protocol(CDTraceLarge)];
    Check(CDXPCTraceRegisterClient(Client(connection),@"bounded protocol"),"large protocol was not observed");
    NSDictionary *summary=Events(@"xpc_protocol_inventory").lastObject;
    Check([summary[@"truncated"] boolValue],"oversized method inventory not marked truncated");
    Check([summary[@"method_count"] unsignedIntegerValue]<=40 && Events(@"xpc_protocol_method").count<=40,
        "method inventory exceeded record bound");
    Check([summary[@"metadata_bytes"] unsignedIntegerValue]<=32768,"method inventory exceeded byte bound");
    NSXPCConnection *empty=Missing(); empty.remoteObjectInterface=nil;
    Check(CDXPCTraceRegisterClient(Client(empty),@"missing protocol"),"nil protocol prevented connection tracing");
    NSDictionary *missing=Events(@"xpc_protocol_inventory").lastObject;
    Check([missing[@"available"] isEqual:@NO] && [missing[@"reason"] isEqual:@"remote_interface_protocol_unavailable"],
        "unavailable protocol metadata was silently omitted");
    [connection invalidate]; [empty invalidate];
}

static void ConcurrentRetryAndLifecycle(void) {
    CDTraceServer *server=[CDTraceServer new]; NSXPCListener *listener=[NSXPCListener anonymousListener];
    listener.delegate=server; [listener resume];
    constexpr int count=8;
    NSMutableArray<CDXPCClientFixture *> *targets=[NSMutableArray array];
    std::atomic<int> replies{0},interruptions{0},invalidations{0};
    auto *repliesPtr=&replies,*interruptionsPtr=&interruptions,*invalidationsPtr=&invalidations;
    for (int index=0;index<count;++index) {
        CDThrowingConnection *connection=[[CDThrowingConnection alloc] initWithListenerEndpoint:listener.endpoint];
        connection.remoteObjectInterface=[NSXPCInterface interfaceWithProtocol:@protocol(CDTraceEcho)];
        connection.interruptionHandler=^{ interruptionsPtr->fetch_add(1); };
        connection.invalidationHandler=^{ invalidationsPtr->fetch_add(1); };
        connection.failInvalidationRead=YES;
        CDXPCClientFixture *client=Client(connection); [targets addObject:client];
        Check(CDXPCTraceRegisterClient(client,@"concurrent setup retry"),"concurrent fixture registration failed");
        [connection resume];
        [[connection remoteObjectProxyWithErrorHandler:^(NSError *error) { (void)error; }]
            echo:@"connected" reply:^(NSString *text) { (void)text; repliesPtr->fetch_add(1); }];
    }
    Check(Wait([&] { return replies.load()==count; }),"concurrent fixture did not connect");
    Check([CDXPCTraceSummary()[@"fully_instrumented_connections"] unsignedIntegerValue]==0,"partial fixture setup hidden");
    // Read the fixture's ivar through a retained local before clearing its throw
    // flag; using the observed getter here would consume a setup retry.
    for (CDXPCClientFixture *client in targets) {
        Ivar ivar=class_getInstanceVariable(CDXPCClientFixture.class,"_serviceConnection");
        CDThrowingConnection *connection=object_getIvar(client,ivar); connection.failInvalidationRead=NO;
    }
    dispatch_group_t group=dispatch_group_create(); dispatch_queue_t queue=dispatch_get_global_queue(QOS_CLASS_DEFAULT,0);
    for (CDXPCClientFixture *client in targets) dispatch_group_async(group,queue,^{ (void)client.serviceConnection; });
    dispatch_group_async(group,queue,^{ [server disconnect]; });
    Check(dispatch_group_wait(group,dispatch_time(DISPATCH_TIME_NOW,5*NSEC_PER_SEC))==0,"retry/lifecycle callback deadlocked");
    Check(Wait([&] { return interruptions.load()==count; }),"concurrent retry lost or duplicated lifecycle callbacks");
    Check(Events(@"xpc_connection_interrupted").count==count,"concurrent retry lost or duplicated lifecycle records");
    Check([CDXPCTraceSummary()[@"fully_instrumented_connections"] unsignedIntegerValue]==count,"successful retries not fully observed");
    CDXPCTraceBeginCleanup();
    for (CDXPCClientFixture *client in targets) [client.serviceConnection invalidate];
    Check(Wait([&] { return invalidations.load()==count; }),"concurrent retry lost original invalidation handlers");
    [listener invalidate];
}

static void SuccessAndUntargeted(void) {
    CDTraceServer *server=[CDTraceServer new]; NSXPCListener *listener=[NSXPCListener anonymousListener];
    listener.delegate=server; [listener resume];
    NSXPCConnection *connection=[[NSXPCConnection alloc] initWithListenerEndpoint:listener.endpoint];
    connection.remoteObjectInterface=[NSXPCInterface interfaceWithProtocol:@protocol(CDTraceEcho)];
    CDXPCClientFixture *client=Client(connection);
    Check(CDXPCTraceRegisterClient(client,@"success"),"could not register owned client");
    [connection resume];
    std::atomic<int> replies{0}, errors{0}, otherErrors{0};
    auto *repliesPtr=&replies, *errorsPtr=&errors, *otherErrorsPtr=&otherErrors;
    [[client.serviceConnection remoteObjectProxyWithErrorHandler:^(NSError *error) {
        (void)error; errorsPtr->fetch_add(1);
    }] echo:@"round trip" reply:^(NSString *text) {
        if ([text isEqual:@"round trip"]) repliesPtr->fetch_add(1);
    }];
    Check(Wait([&] { return replies.load()==1; }),"successful reply changed or disappeared");
    NSXPCConnection *other=Missing(); CDXPCClientFixture *unowned=Client(other); [other resume];
    [[unowned.serviceConnection remoteObjectProxyWithErrorHandler:^(NSError *error) {
        (void)error; otherErrorsPtr->fetch_add(1);
    }] echo:@"unowned" reply:^(NSString *text) { (void)text; }];
    Check(Wait([&] { return otherErrors.load()==1; }),"untracked connection error handler changed");
    Check(errors.load()==0 && Events(@"xpc_proxy_error").count==0,"successful or untracked connection generated trace error");
    Check([CDXPCTraceSummary()[@"connections"] unsignedIntegerValue]==1,"unowned client was registered");
    std::atomic<int> invalidations{0}; auto *invalidationsPtr=&invalidations;
    // A new handler installed after tracing must replace, not discard or append
    // an older user handler. It still receives the genuine invalidation once.
    connection.invalidationHandler=^{ invalidationsPtr->fetch_add(100); };
    connection.invalidationHandler=^{ invalidationsPtr->fetch_add(1); };
    CDXPCTraceBeginCleanup(); [connection invalidate];
    Check(Wait([&] { return invalidations.load()==1; }),"handler replacement or cleanup invalidation changed");
    Check([Events(@"xpc_connection_invalidated").lastObject[@"cleanup"] boolValue],"cleanup invalidation was misclassified");
    [other invalidate]; [listener invalidate]; [server disconnect];
}

static void ReplacementAndConcurrency(void) {
    CDXPCClientFixture *client=Client(Missing());
    Check(CDXPCTraceRegisterClient(client,@"replacement"),"could not register owned client");
    NSXPCConnection *first=client.serviceConnection;
    client.serviceConnection=Missing(); NSXPCConnection *second=client.serviceConnection;
    Check([CDXPCTraceSummary()[@"connections"] unsignedIntegerValue]==2,"replacement connection escaped observation");
    [first resume]; [second resume];
    constexpr int count=40;
    std::atomic<int> errors{0}; auto *errorsPtr=&errors;
    dispatch_apply(count,dispatch_get_global_queue(QOS_CLASS_DEFAULT,0),^(size_t index) {
        NSXPCConnection *connection=index%2?first:second;
        [[connection remoteObjectProxyWithErrorHandler:^(NSError *error) {
            (void)error; errorsPtr->fetch_add(1);
        }] echo:@"concurrent" reply:^(NSString *text) { (void)text; }];
    });
    Check(Wait([&] { return errors.load()==count; }),"concurrent original error handlers lost or duplicated");
    Check(Wait([] { return Events(@"xpc_proxy_error").count==count; }),"concurrent captured errors lost or duplicated");
    NSMutableSet *identities=[NSMutableSet set];
    for (NSDictionary *event in Events(@"xpc_proxy_error")) [identities addObject:event[@"connection_id"]];
    Check(identities.count==2,"replacement connection identity was reused");
    [first invalidate]; [second invalidate];
}

static void Interruption(void) {
    CDTraceServer *server=[CDTraceServer new]; NSXPCListener *listener=[NSXPCListener anonymousListener];
    listener.delegate=server; [listener resume];
    NSXPCConnection *connection=[[NSXPCConnection alloc] initWithListenerEndpoint:listener.endpoint];
    connection.remoteObjectInterface=[NSXPCInterface interfaceWithProtocol:@protocol(CDTraceEcho)];
    CDXPCClientFixture *client=Client(connection);
    std::atomic<int> interruptions{0}, replies{0}; auto *interruptionsPtr=&interruptions, *repliesPtr=&replies;
    connection.interruptionHandler=^{ interruptionsPtr->fetch_add(1); };
    Check(CDXPCTraceRegisterClient(client,@"interruption"),"could not register owned client");
    [connection resume];
    [[client.serviceConnection remoteObjectProxyWithErrorHandler:^(NSError *error) { (void)error; }]
        echo:@"connect" reply:^(NSString *text) { (void)text; repliesPtr->fetch_add(1); }];
    Check(Wait([&] { return replies.load()==1; }),"server not connected");
    [server disconnect];
    Check(Wait([&] { return interruptions.load()==1; }),"original interruption handler was lost");
    Check(Events(@"xpc_connection_interrupted").count==1,"interruption not captured exactly once");
    [connection invalidate]; [listener invalidate];
}

int main(int argc, const char **argv) { @autoreleasepool {
    rows=[NSMutableArray array]; Check(argc==2,"provide a test mode"); NSString *mode=@(argv[1]);
    if ([mode hasPrefix:@"missing-"]) Failure(mode);
    else if ([mode isEqual:@"success-untracked"]) SuccessAndUntargeted();
    else if ([mode isEqual:@"replacement-concurrency"]) ReplacementAndConcurrency();
    else if ([mode isEqual:@"interruption"]) Interruption();
    else if ([mode isEqual:@"error-bounds"]) ErrorBounds();
    else if ([mode isEqual:@"guarded-registration"]) GuardedRegistration();
    else if ([mode isEqual:@"foreign-getter-owner"]) ForeignGetterOwner();
    else if ([mode isEqual:@"handler-setup-failure"]) HandlerSetupFailure();
    else if ([mode isEqual:@"protocol-metadata"]) ProtocolMetadata();
    else if ([mode isEqual:@"protocol-bounds"]) ProtocolBoundsAndUnavailable();
    else if ([mode isEqual:@"concurrent-retry-lifecycle"]) ConcurrentRetryAndLifecycle();
    else Check(false,"unknown mode");
    fprintf(stderr,"PASS: %s\n",argv[1]); return 0;
} }
