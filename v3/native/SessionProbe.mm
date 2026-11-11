#import "Common.h"
#import "NativeIdentity.h"
#import "HostPayload.h"
#import "SessionInspection.h"
#import "HostProfile.h"
#import <objc/runtime.h>
#include <dlfcn.h>
#include <signal.h>
#include <unistd.h>
#include <fcntl.h>
#include <errno.h>
#include "Timing.h"
@interface NSObject (ReceiverCarKit)
- (id)initWithDisplayName:(id)n wiredIPv6Addresses:(id)w wirelessIPv6Addresses:(id)r port:(long long)p carplayWiFiUUID:(id)u deviceIdentifier:(id)i publicKey:(id)k sourceVersion:(id)v wiredCarPlaySimulator:(BOOL)s;
- (void)startSessionWithHost:(id)host completion:(void(^)(BOOL,NSError *))completion;
- (void)cancelRequests;
- (id)currentSession;
- (BOOL)isAuthenticated;
- (BOOL)isActivated;
@end
static volatile sig_atomic_t stopped=0;
static void hardStop(int s){(void)s;_exit(124);}
static void stop(int s){(void)s;stopped=1;}
static void pump(double s){double end=CDClock()+s;while(CDClock()<end)CFRunLoopRunInMode(kCFRunLoopDefaultMode,.03,false);}
int main(int argc,char **argv){@autoreleasepool{
 if(argc==2&&!strcmp(argv[1],"--inspect")){
  signal(SIGALRM,hardStop);signal(SIGPIPE,SIG_IGN);alarm(8);
  NSDictionary *inspection=CDV3InspectCarKitAtPath(@"/System/Library/PrivateFrameworks/CarKit.framework/CarKit");
  CDEmit(@"native_inspection",inspection);alarm(0);return [inspection[@"complete"] boolValue]?0:10;
 }
 if(argc!=4)return 2;
 int port=atoi(argv[1]),duration=atoi(argv[3]);NSString *key=@(argv[2]);
 if(port<1024||port>65535||duration<0||key.length!=64||[key rangeOfCharacterFromSet:[NSCharacterSet characterSetWithCharactersInString:@"0123456789abcdef"].invertedSet].location!=NSNotFound)return 2;
 signal(SIGTERM,stop);signal(SIGINT,stop);signal(SIGHUP,stop);signal(SIGALRM,hardStop);signal(SIGPIPE,SIG_IGN);alarm(20);pid_t parent=getppid();
 if(fcntl(STDIN_FILENO,F_SETFL,fcntl(STDIN_FILENO,F_GETFL)|O_NONBLOCK)<0)return 2;
 CDEmit(@"experimental_target",@{@"machine":CDSystem("hw.machine")?:@"",@"build":CDSystem("kern.osversion")?:@""});
 void *h=dlopen("/System/Library/PrivateFrameworks/CarKit.framework/CarKit",RTLD_NOW|RTLD_LOCAL);if(!h)return 4;
 Class hc=NSClassFromString(@"CARSessionRequestHost"),cc=NSClassFromString(@"CARSessionRequestClient"),sc=NSClassFromString(@"CARSessionStatus");
 NSDictionary *legacyIdentity=CDCarKitCompletionIdentity(cc);
 NSDictionary *profile=CDV3InspectHostProfile(hc,cc,sc,legacyIdentity);
 CDEmit(@"host_profile",profile);
 if(![profile[@"normal_mode_method_checks_passed"] boolValue])return 5;
 NSDictionary *identity=profile[@"completion_identity"];CDEmit(@"completion_identity",identity);if(![identity[@"typed_completion_enabled"] boolValue])return 6;
 id observer=[[sc alloc] init];pump(1);if([observer currentSession]){CDEmit(@"existing_session_withheld",@{});return 7;}
 Timing timing;if(!timing.start()){CDEmit(@"timing_bind_failed",@{});return 9;}
 id client=[[cc alloc] init];
 @try{
 NSError *error=nil;id host=nil;
 if(CDV3UsesDictionaryHostProfile(profile)){
  host=CDV3CreateDictionaryHost(hc,port,key,&error);
  if(!host){CDEmit(@"archive_failed",@{@"error":error.description?:@"",@"stage":@"dictionary_host_preflight"});return 8;}
  CDEmit(@"host_secure_coding",@{@"matches":@YES,@"live_fields_match":@YES,@"public_key_type":@"NSString",@"profile":profile[@"selected_profile"]});
 }else{
  host=[[hc alloc] initWithDisplayName:@"CarDash V3" wiredIPv6Addresses:@[@"::1"] wirelessIPv6Addresses:@[] port:port carplayWiFiUUID:nil deviceIdentifier:@"02:43:44:4c:41:42" publicKey:key sourceVersion:@"509.0" wiredCarPlaySimulator:YES];
  if(!CDSecureHostRoundTrip(host,&error)){CDEmit(@"archive_failed",@{@"error":error.description?:@""});return 8;}
 }
 CDEmit(@"request_started",@{@"port":@(port),@"duration":@(duration),@"pid":@(getpid())});
 [client startSessionWithHost:host completion:^(BOOL success,NSError *error){CDEmit(@"native_completion",@{@"success":@(success),@"error":error.description?:@""});}];
 double start=CDClock(),last=0,lease=start;while(!stopped&&getppid()==parent&&(!duration||CDClock()-start<duration)){@autoreleasepool{
 char heartbeat[64];ssize_t n=read(STDIN_FILENO,heartbeat,sizeof(heartbeat));
 if(n>0){lease=CDClock();alarm(20);}else if(n==0||(n<0&&errno!=EAGAIN&&errno!=EWOULDBLOCK)){CDEmit(@"parent_pipe_closed",@{});break;}
 if(CDClock()-lease>15){CDEmit(@"parent_lease_expired",@{});break;}
 timing.step();if(CDClock()-last>1){id current=[observer currentSession];id authenticated=NSNull.null,activated=NSNull.null;if(current&&CDMethodMatches([current class],@"isAuthenticated","B",@[],NO,YES))authenticated=@([current isAuthenticated]);if(current&&CDMethodMatches([current class],@"isActivated","B",@[],NO,YES))activated=@([current isActivated]);CDEmit(@"session_observation",@{@"present":@(current!=nil),@"authenticated":authenticated,@"activated":activated,@"timing_requests":@(timing.requests),@"timing_replies":@(timing.replies)});last=CDClock();}pump(.02);}}
 }@catch(NSException *e){CDEmit(@"exception",@{@"name":e.name,@"reason":e.reason?:@""});}
 alarm(5);[client cancelRequests];pump(1);CDEmit(@"cleanup",@{@"session_present":@([observer currentSession]!=nil)});return 0;
}}
