#import "Common.h"
#import "XPCTrace.h"
#import "NativeIdentity.h"
#import "HostPayload.h"
#import <objc/runtime.h>
#import <objc/message.h>
#include <dlfcn.h>
#include <fcntl.h>
#include <netinet/in.h>
#include <sys/socket.h>
#include <signal.h>
#include <unistd.h>
#include <asl.h>
#include <atomic>
#include <memory>
#include <vector>
#include <pthread.h>
#include <spawn.h>
#include <sys/wait.h>
#include "PublicKey.h"

@interface NSObject (CDPrivateCarKit)
- (id)initWithHostProperties:(id)properties;
- (id)initWithDisplayName:(id)name wiredIPv6Addresses:(id)wired wirelessIPv6Addresses:(id)wireless port:(long long)port carplayWiFiUUID:(id)wifi deviceIdentifier:(id)identifier publicKey:(id)key sourceVersion:(id)version wiredCarPlaySimulator:(BOOL)simulator;
- (id)displayName;
- (id)deviceIdentifier;
- (void)setWiredCarPlaySimulator:(BOOL)value;
- (BOOL)isWiredCarPlaySimulator;
- (void)setWiredIPv6Addresses:(id)value;
- (id)wiredIPv6Addresses;
- (void)setWirelessIPv6Addresses:(id)value;
- (id)wirelessIPv6Addresses;
- (void)setPort:(long long)value;
- (long long)port;
- (void)setSourceVersion:(id)value;
- (id)sourceVersion;
- (void)setPublicKey:(id)value;
- (id)publicKey;
- (void)startSessionWithHost:(id)host completion:(id)completion;
- (void)cancelRequests;
- (id)currentSession;
- (BOOL)isActivated;
- (BOOL)isAuthenticated;
- (BOOL)isPaired;
@end
static volatile sig_atomic_t stopWorker=0;
static void Stop(int sig){(void)sig;stopWorker=1;}
static void Pump(double seconds){double end=CDClock()+seconds;while(!stopWorker&&CDClock()<end){CFRunLoopRunInMode(kCFRunLoopDefaultMode,.03,false);usleep(10000);}}
static BOOL StartGate(void){if(stopWorker){CDEmit(@"request_withheld_cancelled",@{});return NO;}return YES;}
static volatile sig_atomic_t ownedGroup=0;
static void GuardEnd(int signal){(void)signal;if(ownedGroup>1)kill(-ownedGroup,SIGKILL);_exit(124);}
struct Guard {pid_t parent;double deadline;};
static void *WatchParent(void *raw){Guard *guard=(Guard *)raw;for(;;){if(getppid()!=guard->parent||CDClock()>guard->deadline)GuardEnd(0);usleep(50000);}return NULL;}
BOOL CDInstallWorkerGuard(unsigned seconds){
    if(getpgrp()!=getpid()||getppid()<=1)return NO;
    ownedGroup=getpid();signal(SIGALRM,GuardEnd);sigset_t signals;sigemptyset(&signals);sigaddset(&signals,SIGALRM);pthread_sigmask(SIG_UNBLOCK,&signals,NULL);alarm(seconds);
    Guard *guard=new Guard{getppid(),CDClock()+seconds};pthread_t thread;int result=pthread_create(&thread,NULL,WatchParent,guard);
    if(result){delete guard;return NO;}pthread_detach(thread);return YES;
}
int CDLogWorker(void){
    signal(SIGTERM,Stop);signal(SIGINT,Stop);signal(SIGPIPE,SIG_IGN);
    const char *tool=NULL;for(const char *path:{"/usr/bin/log","/var/jb/usr/bin/log"})if(access(path,X_OK)==0){tool=path;break;}if(!tool)return 2;
    const char *args[]={tool,"stream","--style","ndjson","--level","debug","--predicate","process == 'carkitd' OR process == 'accessoryd' OR process == 'CarPlay' OR subsystem CONTAINS[c] 'CarPlay' OR subsystem CONTAINS[c] 'CarKit'",NULL};
    extern char **environ;pid_t child;
    // The collector inherits this worker's private group. The independent
    // guardian kills the whole group on parent loss or hard deadline.
    int error=posix_spawn(&child,tool,NULL,NULL,(char *const *)args,environ);if(error)return 2;
    for(;;){int status=0;pid_t got=waitpid(child,&status,WNOHANG);if(got==child)return WIFEXITED(status)?WEXITSTATUS(status):1;if(got<0&&errno!=EINTR)return 1;if(stopWorker)GuardEnd(0);usleep(10000);}
}
#if !CD_HOST_TEST
static BOOL Match(Class cls,NSString *name,const char *ret,NSArray *args,BOOL classMethod=NO){return CDMethodMatches(cls,name,ret,args,classMethod,YES);}
static NSArray *HostMethods(void){return @[
    @[@"initWithDisplayName:wiredIPv6Addresses:wirelessIPv6Addresses:port:carplayWiFiUUID:deviceIdentifier:publicKey:sourceVersion:wiredCarPlaySimulator:",@"@",@[@"@",@"@",@"@",@"q",@"@",@"@",@"@",@"@",@"B"]],@[@"displayName",@"@",@[]],@[@"deviceIdentifier",@"@",@[]],
    @[@"initWithHostProperties:",@"@",@[@"@"]],@[@"setWiredCarPlaySimulator:",@"v",@[@"B"]],@[@"isWiredCarPlaySimulator",@"B",@[]],
    @[@"setWiredIPv6Addresses:",@"v",@[@"@"]],@[@"wiredIPv6Addresses",@"@",@[]],@[@"setWirelessIPv6Addresses:",@"v",@[@"@"]],@[@"wirelessIPv6Addresses",@"@",@[]],
    @[@"setPort:",@"v",@[@"q"]],@[@"port",@"q",@[]],@[@"setSourceVersion:",@"v",@[@"@"]],@[@"sourceVersion",@"@",@[]],@[@"setPublicKey:",@"v",@[@"@"]],@[@"publicKey",@"@",@[]]];}
static BOOL CheckMethods(Class cls,NSArray *specs){
    BOOL valid=cls!=Nil;
    const char *image=cls?class_getImageName(cls):NULL;
    if(!image||!strstr(image,"/CarKit.framework/"))valid=NO;
    for(NSArray *spec in specs){Method method=class_getInstanceMethod(cls,NSSelectorFromString(spec[0]));Dl_info owner={};if(method)dladdr((const void *)method_getImplementation(method),&owner);
        BOOL ok=Match(cls,spec[0],[spec[1] UTF8String],spec[2]);valid=valid&&ok;
        CDEmit(@"method_abi",@{@"class":cls?NSStringFromClass(cls):@"absent",@"selector":spec[0],@"encoding":method?@(method_getTypeEncoding(method)):@"",@"owner":owner.dli_fname?@(owner.dli_fname):@"",@"matches":@(ok)});
    }return valid;
}
static BOOL Load(NSString *name,NSString *path){dlerror();void *handle=dlopen(path.fileSystemRepresentation,RTLD_NOW|RTLD_LOCAL);const char *error=dlerror();CDEmit(@"framework",@{@"name":name,@"path":path,@"loaded":@(handle!=NULL),@"error":error?@(error):@""});return handle!=NULL;}
static NSDictionary *Session(id observer){
    id session=[observer currentSession];NSMutableDictionary *value=[@{@"present":@(session!=nil)} mutableCopy];
    if(session){Class cls=[session class];for(NSString *name in @[@"isActivated",@"isAuthenticated",@"isPaired"]){
        if(Match(cls,name,"B",@[]))value[name]=@(((BOOL(*)(id,SEL))objc_msgSend)(session,NSSelectorFromString(name)));else value[name]=@"unavailable";}}
    return value;
}
static id Observer(void){Class cls=NSClassFromString(@"CARSessionStatus");if(!CheckMethods(cls,@[@[@"init",@"@",@[]],@[@"currentSession",@"@",@[]]]))return nil;return [[cls alloc] init];}
static void ClassInventory(NSString *needle){
    unsigned count=0;Class *classes=objc_copyClassList(&count);NSMutableArray *rows=[NSMutableArray array];
    for(unsigned i=0;i<count&&rows.count<24;i++){const char *image=class_getImageName(classes[i]);if(!image||!strstr(image,needle.UTF8String))continue;
        NSString *name=NSStringFromClass(classes[i]);if(![name containsString:@"Session"]&&![name containsString:@"Receiver"]&&![name containsString:@"CarPlay"]&&![name containsString:@"Host"])continue;
        unsigned total=0;Method *methods=class_copyMethodList(classes[i],&total);NSMutableArray *descriptions=[NSMutableArray array];
        for(unsigned j=0;j<MIN(total,60u);j++)[descriptions addObject:@{@"selector":NSStringFromSelector(method_getName(methods[j])),@"encoding":@(method_getTypeEncoding(methods[j]))}];free(methods);
        [rows addObject:name];CDEmit(@"class_methods",@{@"class":name,@"method_count":@(total),@"methods":descriptions});}
    free(classes);CDEmit(@"class_inventory",@{@"framework":needle,@"classes":rows,@"limit":@24});
}
static void ServiceInventory(void){
    NSString *directory=@"/System/Library/LaunchDaemons";NSError *error=nil;
    NSArray *names=[[NSFileManager.defaultManager contentsOfDirectoryAtPath:directory error:&error] sortedArrayUsingSelector:@selector(compare:)];
    if(!names){CDEmit(@"service_inventory",@{@"available":@NO,@"error":CDXPCTraceError(error)});return;}
    NSUInteger examined=0,bytes=0,matched=0,unreadable=0;BOOL truncated=NO;
    for(NSString *name in names){
        if(![name.pathExtension isEqual:@"plist"])continue;
        if(examined>=512||bytes>=4*1024*1024||matched>=24){truncated=YES;break;}examined++;
        NSString *path=[directory stringByAppendingPathComponent:name];NSDictionary *attributes=[NSFileManager.defaultManager attributesOfItemAtPath:path error:NULL];
        if(![attributes[NSFileType] isEqual:NSFileTypeRegular]||[attributes[NSFileSize] unsignedLongLongValue]>128*1024){unreadable++;continue;}
        NSData *data=[NSData dataWithContentsOfFile:path options:0 error:NULL];if(!data){unreadable++;continue;}bytes+=data.length;
        id value=[NSPropertyListSerialization propertyListWithData:data options:NSPropertyListImmutable format:NULL error:NULL];
        if(![value isKindOfClass:NSDictionary.class]){unreadable++;continue;}
        NSDictionary *job=value;id services=job[@"MachServices"];if(![services isKindOfClass:NSDictionary.class])continue;
        NSMutableArray *selected=[NSMutableArray array];
        for(id key in services)if([key isKindOfClass:NSString.class]&&[key length]<256&&[[key lowercaseString] containsString:@"carkit"]&&selected.count<16)[selected addObject:key];
        if(!selected.count)continue;
        NSMutableDictionary *row=[@{@"path":path,@"services":selected,@"configured_only_not_proof_running":@YES} mutableCopy];
        for(NSString *key in @[@"Label",@"Program"]){id text=job[key];if([text isKindOfClass:NSString.class]&&[text length]<512)row[key]=text;}
        id args=job[@"ProgramArguments"];NSMutableArray *safeArgs=[NSMutableArray array];
        if([args isKindOfClass:NSArray.class])for(id arg in args){if(safeArgs.count>=6)break;if([arg isKindOfClass:NSString.class]&&[arg length]<512)[safeArgs addObject:arg];}
        row[@"ProgramArguments"]=safeArgs;CDEmit(@"configured_carkit_service",row);matched++;
    }
    CDEmit(@"service_inventory",@{@"available":@YES,@"examined":@(examined),@"bytes_read":@(bytes),@"matches":@(matched),@"unreadable_or_skipped":@(unreadable),@"truncated":@(truncated)});
}
static void Displays(void){
    if(!Load(@"QuartzCore",@"/System/Library/Frameworks/QuartzCore.framework/QuartzCore"))return;
    Class cls=NSClassFromString(@"CADisplay");
    if(!Match(cls,@"displays","@",@[],YES)){CDEmit(@"display_inventory_unavailable",@{});return;}
    id value=((id(*)(id,SEL))objc_msgSend)(cls,NSSelectorFromString(@"displays"));
    if(![value isKindOfClass:NSArray.class])return;NSMutableArray *rows=[NSMutableArray array];
    for(id display in value){if(rows.count>=8)break;NSMutableDictionary *row=[NSMutableDictionary dictionary];Class type=[display class];
        if(Match(type,@"displayId","I",@[]))row[@"display_id"]=@(((unsigned(*)(id,SEL))objc_msgSend)(display,NSSelectorFromString(@"displayId")));
        if(Match(type,@"isExternal","B",@[]))row[@"external"]=@(((BOOL(*)(id,SEL))objc_msgSend)(display,NSSelectorFromString(@"isExternal")));
        if(Match(type,@"displayType","q",@[]))row[@"display_type"]=@(((long long(*)(id,SEL))objc_msgSend)(display,NSSelectorFromString(@"displayType")));
        [rows addObject:row];}
    CDEmit(@"display_inventory",@{@"count":@([value count]),@"displays":rows,@"live_frame_verified":@NO});
}
static void LegacyLogs(void){
    NSUInteger found=0;
    for(const char *sender: {"carkitd","accessoryd","CarPlay"}){
        aslmsg query=asl_new(ASL_TYPE_QUERY);char since[32];snprintf(since,sizeof(since),"%lld",(long long)time(NULL)-180);
        asl_set_query(query,ASL_KEY_SENDER,sender,ASL_QUERY_OP_EQUAL);asl_set_query(query,ASL_KEY_TIME,since,ASL_QUERY_OP_GREATER_EQUAL|ASL_QUERY_OP_NUMERIC);
        aslresponse response=asl_search(NULL,query);aslmsg row;
        while(response&&(row=aslresponse_next(response))&&found<200){const char *message=asl_get(row,ASL_KEY_MSG),*date=asl_get(row,ASL_KEY_TIME);
            NSString *text=message?@(message):@"";if(text.length>2000)text=[text substringToIndex:2000];CDEmit(@"legacy_service_log",@{@"sender":@(sender),@"time":date?@(date):@"",@"message":text});found++;}
        if(response)aslresponse_free(response);asl_free(query);
    }CDEmit(@"legacy_log_summary",@{@"records":@(found),@"note":@"ASL may not expose unified logs on this OS; zero records is not evidence of no service error"});
}
struct Connection {int fd;NSMutableData *header;};
static int Attempt(NSString *profile){
    Class hostClass=NSClassFromString(@"CARSessionRequestHost"),clientClass=NSClassFromString(@"CARSessionRequestClient");
    BOOL valid=CheckMethods(hostClass,HostMethods())&&CheckMethods(clientClass,@[@[@"init",@"@",@[]],@[@"startSessionWithHost:completion:",@"v",@[@"@",@"@?"]],@[@"cancelRequests",@"v",@[]]]);
    if(!valid){CDEmit(@"request_withheld",@{@"reason":@"ABI or method owner mismatch"});return 21;}
    id observer=Observer();if(!observer){CDEmit(@"request_withheld",@{@"reason":@"Cannot establish pre-existing session state"});return 21;}
    Pump(1);NSDictionary *before=Session(observer);CDEmit(@"session_before",before);
    if(!StartGate())return 0;
    if([before[@"present"] boolValue]){CDEmit(@"request_withheld",@{@"reason":@"An existing CarPlay session must be disconnected before this diagnostic"});return 20;}
    int listener=socket(AF_INET6,SOCK_STREAM,0);if(listener<0)return 1;
    fcntl(listener,F_SETFL,O_NONBLOCK);fcntl(listener,F_SETFD,FD_CLOEXEC);int yes=1;setsockopt(listener,IPPROTO_IPV6,IPV6_V6ONLY,&yes,sizeof(yes));
    struct sockaddr_in6 address={};address.sin6_family=AF_INET6;address.sin6_addr=in6addr_loopback;address.sin6_port=0;
    if(bind(listener,(struct sockaddr *)&address,sizeof(address))||listen(listener,4)){CDEmit(@"listener_failed",@{@"errno":@(errno)});close(listener);return 1;}
    socklen_t size=sizeof(address);if(getsockname(listener,(struct sockaddr *)&address,&size)){close(listener);return 1;}
    long long port=ntohs(address.sin6_port);BOOL simulator=![profile isEqual:@"root-standard-key"],keyed=![profile hasSuffix:@"no-key"];
    CDEmit(@"listener_ready",@{@"address":@"::1",@"port":@(port),@"simulator":@(simulator),@"public_key_present":@(keyed),@"public_key_is_trusted_accessory_identity":@NO});
    id client=nil;BOOL issued=NO,transport=NO,newSession=NO,cleanupConfirmed=NO;std::vector<Connection> clients;
    auto callback=std::make_shared<std::atomic<bool>>(false),nativeSuccess=std::make_shared<std::atomic<bool>>(false);
    BOOL typedCompletion=NO;
    @try {
        NSString *publicKey=keyed?CDPublicKeyString([NSData dataWithBytes:CDPublicKey length:32]):nil;
        NSObject *host=[[hostClass alloc] initWithDisplayName:@"CarDash Diagnostics" wiredIPv6Addresses:@[@"::1"] wirelessIPv6Addresses:@[] port:port carplayWiFiUUID:nil deviceIdentifier:@"02:43:44:44:49:41" publicKey:publicKey sourceVersion:@"509.0" wiredCarPlaySimulator:simulator];
        client=[[clientClass alloc] init];if(!host||!client)@throw [NSException exceptionWithName:@"AllocationFailure" reason:@"CarKit initialization returned nil" userInfo:nil];
        BOOL roundtrip=[host isWiredCarPlaySimulator]==simulator&&[host port]==port&&[[host wiredIPv6Addresses] isEqual:@[@"::1"]]&&[[host wirelessIPv6Addresses] count]==0&&[[host sourceVersion] isEqual:@"509.0"]&&(keyed?[[host publicKey] isEqual:publicKey]:[host publicKey]==nil);
        CDEmit(@"host_roundtrip",@{@"matches":@(roundtrip)});if(!roundtrip)@throw [NSException exceptionWithName:@"HostMismatch" reason:@"Host setters did not round trip" userInfo:nil];
        NSError *archiveError=nil;NSObject *decoded=CDSecureHostRoundTrip(host,&archiveError);
        BOOL wireMatches=decoded&&[decoded isWiredCarPlaySimulator]==simulator&&[decoded port]==port&&[[decoded wiredIPv6Addresses] isEqual:@[@"::1"]]&&[[decoded wirelessIPv6Addresses] isEqual:@[]]&&[[decoded sourceVersion] isEqual:@"509.0"]&&[[decoded displayName] isEqual:@"CarDash Diagnostics"]&&[[decoded deviceIdentifier] isEqual:@"02:43:44:44:49:41"]&&(keyed?[[decoded publicKey] isEqual:publicKey]:[decoded publicKey]==nil);
        CDEmit(@"host_secure_coding",@{@"matches":@(wireMatches),@"public_key_type":publicKey?@"NSString":@"nil",@"public_key_encoding":publicKey?@"hex_32_bytes":@"none",@"synthetic_device_identifier":@YES,@"error":CDXPCTraceError(archiveError)});
        if(!wireMatches)@throw [NSException exceptionWithName:@"HostWireMismatch" reason:@"Host failed local secure-coding round trip; request withheld" userInfo:nil];
        NSDictionary *identity=CDCarKitCompletionIdentity(clientClass);CDEmit(@"completion_identity",identity);typedCompletion=[identity[@"typed_completion_enabled"] boolValue];
        BOOL traceRegistered=CDXPCTraceRegisterClient(client,profile);CDEmit(@"xpc_trace_registration",@{@"registered":@(traceRegistered)});
        auto mainAlive=std::make_shared<std::atomic<bool>>(false);
        dispatch_async(dispatch_get_main_queue(),^{mainAlive->store(true);CDEmit(@"main_queue_marker",@{@"main_thread":@(NSThread.isMainThread)});});Pump(.1);
        CDEmit(@"request_queue",@{@"main_thread":@(NSThread.isMainThread),@"main_queue_marker_observed":@(mainAlive->load())});
        if(!StartGate())@throw [NSException exceptionWithName:@"Cancelled" reason:@"Cancelled before native start" userInfo:nil];
        CDEmit(@"start_call_enter",@{@"profile":profile});issued=YES;
        if(typedCompletion){
            [client startSessionWithHost:host completion:^(BOOL success,NSError *error){
                nativeSuccess->store(success);callback->store(true);
                CDEmit(@"native_completion",@{@"arguments_interpreted":@YES,@"success":@(success),@"error":CDXPCTraceError(error)});
            }];
        }else{
            // A method encoding only identifies a block, not its nested ABI.
            // Preserve occurrence-only observation for any unknown image pair.
            [client startSessionWithHost:host completion:^{callback->store(true);CDEmit(@"native_completion",@{@"arguments_interpreted":@NO});}];
        }
        CDEmit(@"start_call_returned",@{});double end=CDClock()+18,lastSnapshot=0;
        while(!stopWorker&&CDClock()<end){
            for(int i=0;i<4;i++){struct sockaddr_in6 peer={};socklen_t len=sizeof(peer);int fd=accept(listener,(struct sockaddr *)&peer,&len);if(fd<0)break;
                if(peer.sin6_family!=AF_INET6||!IN6_IS_ADDR_LOOPBACK(&peer.sin6_addr)||clients.size()>=4){close(fd);continue;}
                fcntl(fd,F_SETFL,O_NONBLOCK);setsockopt(fd,SOL_SOCKET,SO_NOSIGPIPE,&yes,sizeof(yes));clients.push_back({fd,[NSMutableData data]});transport=YES;CDEmit(@"loopback_connected",@{@"peer_loopback":@YES});}
            for(auto it=clients.begin();it!=clients.end();){BOOL closeConnection=NO;char b[4096];ssize_t n=recv(it->fd,b,sizeof(b),0);
                if(n>0){[it->header appendBytes:b length:n];if(it->header.length>16384){CDEmit(@"receiver_header_limit",@{});closeConnection=YES;}
                    NSString *text=[[NSString alloc] initWithData:it->header encoding:NSUTF8StringEncoding];
                    if(text&&[text containsString:@"\r\n\r\n"]){NSString *first=[[text componentsSeparatedByString:@"\r\n"] firstObject];NSArray *parts=[first componentsSeparatedByString:@" "];
                        NSString *method=parts.count?parts[0]:@"unknown",*path=parts.count>1?[[parts[1] componentsSeparatedByString:@"?"] firstObject]:@"";
                        if(method.length>32)method=@"unrecognized";if(path.length>128)path=[path substringToIndex:128];
                        BOOL rtsp=[first hasSuffix:@"RTSP/1.0"],options=[method isEqual:@"OPTIONS"];NSString *cseq=@"";
                        for(NSString *line in [text componentsSeparatedByString:@"\r\n"])if([[line lowercaseString] hasPrefix:@"cseq:"]){NSString *v=[[line substringFromIndex:5] stringByTrimmingCharactersInSet:NSCharacterSet.whitespaceCharacterSet];if(v.length<12&&[v rangeOfCharacterFromSet:NSCharacterSet.decimalDigitCharacterSet.invertedSet].location==NSNotFound)cseq=[NSString stringWithFormat:@"CSeq: %@\r\n",v];}
                        CDEmit(@"receiver_request",@{@"method":method,@"path":path,@"protocol":rtsp?@"RTSP/1.0":@"HTTP/1.1",@"response_status":options?@200:@501,@"authentication_implemented":@NO});
                        NSString *reply=[NSString stringWithFormat:@"%@ %@\r\n%@Content-Length: 0\r\nConnection: close\r\n\r\n",rtsp?@"RTSP/1.0":@"HTTP/1.1",options?@"200 OK":@"501 Diagnostic Receiver Only",cseq];send(it->fd,reply.UTF8String,strlen(reply.UTF8String),0);closeConnection=YES;
                    }
                }else if(n==0||(n<0&&errno!=EAGAIN&&errno!=EWOULDBLOCK&&errno!=EINTR))closeConnection=YES;
                if(closeConnection){close(it->fd);it=clients.erase(it);}else ++it;
            }
            if(CDClock()-lastSnapshot>2){NSDictionary *value=Session(observer);CDEmit(@"session_observation",value);newSession=newSession||[value[@"present"] boolValue];lastSnapshot=CDClock();}
            Pump(.04);
        }
    }@catch(NSException *exception){CDEmit(@"native_exception",@{@"name":exception.name?:@"",@"reason":exception.reason?:@""});}
    // Even a blocked/throwing cancellation is isolated and killed by the parent deadline.
    CDXPCTraceBeginCleanup();
    if(client){CDEmit(@"cancel_call_enter",@{});@try{[client cancelRequests];cleanupConfirmed=YES;CDEmit(@"cancel_call_returned",@{});}@catch(NSException *e){CDEmit(@"cancel_exception",@{@"name":e.name});}}
    for(auto &c:clients)close(c.fd);close(listener);Pump(.5);NSDictionary *after=Session(observer);CDEmit(@"session_after_cleanup",after);
    NSDictionary *trace=CDXPCTraceSummary();CDEmit(@"xpc_trace_summary",trace);
    CDEmit(@"native_summary",@{@"profile":profile,@"request_issued":@(issued),@"callback_observed":@(callback->load()),@"completion_arguments_enabled":@(typedCompletion),@"native_success":typedCompletion&&callback->load()?@(nativeSuccess->load()):(id)NSNull.null,@"xpc_trace":trace,@"transport_connected":@(transport),@"new_session_observed":@(newSession),@"request_cancel_returned":@(cleanupConfirmed),@"session_still_present":after[@"present"],@"live_carplay_verified":@NO,@"conclusion":CDConclusion(issued,callback->load(),transport,newSession)});
    if(stopWorker&&!issued)return 0;
    return [after[@"present"] boolValue]?23:issued&&cleanupConfirmed?0:1;
}
#endif
int CDWorker(NSString *profile){@autoreleasepool{
    signal(SIGPIPE,SIG_IGN);signal(SIGTERM,Stop);signal(SIGINT,Stop);
#if CD_HOST_TEST
    NSString *mode=@(getenv("CD_TEST_WORKER_MODE")?:"normal");CDEmit(@"host_fixture",@{@"mode":mode,@"native_session_attempted":@NO});
    if([mode isEqual:@"hang"]){while(!stopWorker)usleep(10000);return 0;}
    if([mode isEqual:@"descendant"]){const char *args[]={"/bin/sleep","30",NULL};extern char **environ;pid_t child;if(posix_spawn(&child,args[0],NULL,NULL,(char *const *)args,environ))return 1;CDEmit(@"owned_descendant",@{@"pid":@(child)});while(!stopWorker)usleep(10000);kill(child,SIGTERM);while(waitpid(child,NULL,0)<0&&errno==EINTR){}return 0;}
    if([mode isEqual:@"crash"]){raise(SIGABRT);return 1;}
    if([mode isEqual:@"cancel-baseline"]){CDEmit(@"baseline_enter",@{});Pump(.45);if(StartGate())CDEmit(@"start_call_enter",@{@"test_fixture":@YES});return 0;}
    if([mode isEqual:@"noisy"]){char block[8192];memset(block,'x',sizeof(block));for(int i=0;i<900&&!stopWorker;i++)write(STDOUT_FILENO,block,sizeof(block));return 0;}
    usleep(120000);CDEmit(@"host_fixture_complete",@{@"profile":profile});return 0;
#else
    CDEmit(@"worker_environment",@{@"profile":profile,@"model":CDSystem("hw.machine"),@"build":CDSystem("kern.osversion"),@"uid":@(getuid()),@"euid":@(geteuid())});
    NSDictionary *ipc=CDIPCEnvironment();CDEmit(@"worker_ipc_environment",ipc);
    if([profile hasPrefix:@"root-simulator-entitlement-"]&&![ipc[@"signed_entitlements"][@"com.apple.private.carkit.sessionRequest"] isEqual:@YES]){
        CDEmit(@"request_withheld",@{@"reason":@"entitlement_comparison_invalid_effective_value_not_true"});return 21;
    }
    if(![CDSystem("hw.machine") isEqual:@"iPhone10,2"]||![CDSystem("kern.osversion") isEqual:@"20G75"]){CDEmit(@"unsupported_target",@{@"expected":@"iPhone10,2 / 20G75",@"private_calls_withheld":@YES});return 21;}
    @try{
        if([profile isEqual:@"displays"]){Displays();return 0;}
        if([profile isEqual:@"receiver"]){if(Load(@"AirPlayReceiver",@"/System/Library/PrivateFrameworks/AirPlayReceiver.framework/AirPlayReceiver"))ClassInventory(@"AirPlayReceiver.framework");return 0;}
        if([profile isEqual:@"system-log-fallback"]){LegacyLogs();return 0;}
        if(!Load(@"CarKit",@"/System/Library/PrivateFrameworks/CarKit.framework/CarKit"))return 21;
        if([profile isEqual:@"inventory"]){ServiceInventory();ClassInventory(@"CarKit.framework");id observer=Observer();if(observer){Pump(1);CDEmit(@"session_inventory",Session(observer));}return 0;}
        if([@[@"root-simulator-key",@"root-simulator-no-key",@"root-standard-key",@"mobile-simulator-key",@"root-simulator-entitlement-key",@"root-simulator-entitlement-no-key",@"root-simulator-baseline-after-key"] containsObject:profile])return Attempt(profile);
        CDEmit(@"unknown_profile",@{});return 2;
    }@catch(NSException *e){CDEmit(@"worker_exception",@{@"name":e.name,@"reason":e.reason?:@""});return 1;}
#endif
}}
