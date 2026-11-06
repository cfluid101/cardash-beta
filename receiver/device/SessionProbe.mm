#import "Common.h"
#import "NativeIdentity.h"
#import "HostPayload.h"
#import <objc/runtime.h>
#include <dlfcn.h>
#include <signal.h>
#include <unistd.h>
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
 if(argc!=4)return 2;
 int port=atoi(argv[1]),duration=atoi(argv[3]);NSString *key=@(argv[2]);
 if(port<1024||port>65535||duration<5||duration>300||key.length!=64||[key rangeOfCharacterFromSet:[NSCharacterSet characterSetWithCharactersInString:@"0123456789abcdef"].invertedSet].location!=NSNotFound)return 2;
 signal(SIGTERM,stop);signal(SIGINT,stop);signal(SIGHUP,stop);signal(SIGALRM,hardStop);signal(SIGPIPE,SIG_IGN);alarm(duration+5);pid_t parent=getppid();
 if(![CDSystem("hw.machine") isEqual:@"iPhone10,2"]||![CDSystem("kern.osversion") isEqual:@"20G75"]){CDEmit(@"wrong_target",@{});return 3;}
 void *h=dlopen("/System/Library/PrivateFrameworks/CarKit.framework/CarKit",RTLD_NOW|RTLD_LOCAL);if(!h)return 4;
 Class hc=NSClassFromString(@"CARSessionRequestHost"),cc=NSClassFromString(@"CARSessionRequestClient"),sc=NSClassFromString(@"CARSessionStatus");
 NSString *selector=@"initWithDisplayName:wiredIPv6Addresses:wirelessIPv6Addresses:port:carplayWiFiUUID:deviceIdentifier:publicKey:sourceVersion:wiredCarPlaySimulator:";
 if(!CDMethodMatches(hc,selector,"@",@[@"@",@"@",@"@",@"q",@"@",@"@",@"@",@"@",@"B"],NO,YES)||!CDMethodMatches(sc,@"currentSession","@",@[],NO,YES)||!CDMethodMatches(cc,@"cancelRequests","v",@[],NO,YES))return 5;
 NSDictionary *identity=CDCarKitCompletionIdentity(cc);CDEmit(@"completion_identity",identity);if(![identity[@"typed_completion_enabled"] boolValue])return 6;
 id observer=[[sc alloc] init];pump(1);if([observer currentSession]){CDEmit(@"existing_session_withheld",@{});return 7;}
 Timing timing;if(!timing.start()){CDEmit(@"timing_bind_failed",@{});return 9;}
 id client=[[cc alloc] init];
 @try{
 id host=[[hc alloc] initWithDisplayName:@"CarDash Native Research" wiredIPv6Addresses:@[@"::1"] wirelessIPv6Addresses:@[] port:port carplayWiFiUUID:nil deviceIdentifier:@"02:43:44:4c:41:42" publicKey:key sourceVersion:@"509.0" wiredCarPlaySimulator:YES];
 NSError *error=nil;if(!CDSecureHostRoundTrip(host,&error)){CDEmit(@"archive_failed",@{@"error":error.description?:@""});return 8;}
 CDEmit(@"request_started",@{@"port":@(port),@"duration":@(duration),@"pid":@(getpid())});
 [client startSessionWithHost:host completion:^(BOOL success,NSError *error){CDEmit(@"native_completion",@{@"success":@(success),@"error":error.description?:@""});}];
 double start=CDClock(),last=0;while(!stopped&&getppid()==parent&&CDClock()-start<duration){timing.step();if(CDClock()-last>1){id current=[observer currentSession];id authenticated=NSNull.null,activated=NSNull.null;if(current&&CDMethodMatches([current class],@"isAuthenticated","B",@[],NO,YES))authenticated=@([current isAuthenticated]);if(current&&CDMethodMatches([current class],@"isActivated","B",@[],NO,YES))activated=@([current isActivated]);CDEmit(@"session_observation",@{@"present":@(current!=nil),@"authenticated":authenticated,@"activated":activated,@"timing_requests":@(timing.requests),@"timing_replies":@(timing.replies)});last=CDClock();}pump(.02);}
 }@catch(NSException *e){CDEmit(@"exception",@{@"name":e.name,@"reason":e.reason?:@""});}
 [client cancelRequests];pump(1);CDEmit(@"cleanup",@{@"session_present":@([observer currentSession]!=nil)});return 0;
}}
