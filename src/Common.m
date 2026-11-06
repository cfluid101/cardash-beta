#import "Common.h"
#import <objc/runtime.h>
#include <dlfcn.h>
#include <sys/sysctl.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <time.h>
#include <unistd.h>

NSString *CDRoot(void) {
#if CD_HOST_TEST || CD_SIM_TEST
    const char *root=getenv("CD_DIAG_ROOT");
    if(root && root[0]=='/')return @(root);
#endif
    return CD_ROOT;
}
NSString *CDSystem(const char *name) { char value[256]={0};size_t n=sizeof(value);return sysctlbyname(name,value,&n,NULL,0)==0?@(value):@"unavailable"; }
double CDClock(void) { struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);return t.tv_sec+t.tv_nsec/1e9; }
NSData *CDJSON(id object) {
    NSData *data=[NSJSONSerialization dataWithJSONObject:object options:NSJSONWritingSortedKeys error:NULL];
    NSMutableData *out=[NSMutableData dataWithData:data?:[@"{\"error\":\"serialization failed\"}" dataUsingEncoding:NSUTF8StringEncoding]];
    [out appendBytes:"\n" length:1];return out;
}
BOOL CDWrite(int fd,NSData *data) {
    const char *bytes=(const char *)data.bytes;size_t left=data.length;
    while(left){ssize_t n=write(fd,bytes,left);if(n<0&&errno==EINTR)continue;if(n<=0)return NO;bytes+=n;left-=n;}return YES;
}
void CDEmit(NSString *event,NSDictionary *fields) {
    NSMutableDictionary *row=[fields mutableCopy];row[@"event"]=event;row[@"monotonic_seconds"]=@(CDClock());CDWrite(STDOUT_FILENO,CDJSON(row));
}
BOOL CDMethodMatches(Class cls,NSString *selector,const char *ret,NSArray<NSString *> *args,BOOL classMethod,BOOL checkOwner) {
    Method m=classMethod?class_getClassMethod(cls,NSSelectorFromString(selector)):class_getInstanceMethod(cls,NSSelectorFromString(selector));
    if(!m)return NO;
    NSMethodSignature *s=[NSMethodSignature signatureWithObjCTypes:method_getTypeEncoding(m)];
    if(strcmp(s.methodReturnType,ret)||s.numberOfArguments!=args.count+2)return NO;
    for(NSUInteger i=0;i<args.count;i++)if(strcmp([s getArgumentTypeAtIndex:i+2],args[i].UTF8String))return NO;
    if(checkOwner){Dl_info info={};if(!dladdr((const void *)method_getImplementation(m),&info)||!info.dli_fname)return NO;
        NSString *owner=@(info.dli_fname);
        if(![owner hasPrefix:@"/System/Library/"]&&![owner hasPrefix:@"/usr/lib/"])return NO;
        // Private CarKit methods must still be implemented in CarKit. NSObject
        // allocation/initialization may legitimately be inherited from libobjc.
        if(![selector isEqual:@"alloc"]&&![selector isEqual:@"init"]&&[NSStringFromClass(cls) hasPrefix:@"CAR"]&&![owner containsString:@"/CarKit.framework/"])return NO;
    }
    return YES;
}
NSString *CDConclusion(BOOL issued,BOOL callback,BOOL transport,BOOL newSession) {
    if(newSession)return @"new_session_observed_not_live_video_verified";
    if(transport)return @"loopback_reached_authentication_not_implemented";
    if(callback)return @"callback_observed_without_transport";
    return issued?@"request_issued_no_callback_or_transport":@"request_withheld";
}
NSDictionary *CDCommand(NSString *command) {
    int fd=socket(AF_UNIX,SOCK_STREAM,0);if(fd<0)return @{@"error":@"Cannot create helper socket"};
    struct timeval timeout={3,0};setsockopt(fd,SOL_SOCKET,SO_RCVTIMEO,&timeout,sizeof(timeout));setsockopt(fd,SOL_SOCKET,SO_SNDTIMEO,&timeout,sizeof(timeout));
    int yes=1;setsockopt(fd,SOL_SOCKET,SO_NOSIGPIPE,&yes,sizeof(yes));
    struct sockaddr_un address={};address.sun_family=AF_UNIX;NSString *path=[CDRoot() stringByAppendingPathComponent:@"control.sock"];
    if(path.length>=sizeof(address.sun_path)){close(fd);return @{@"error":@"Helper socket path is too long"};}
    strlcpy(address.sun_path,path.fileSystemRepresentation,sizeof(address.sun_path));
    if(connect(fd,(struct sockaddr *)&address,sizeof(address))<0){int code=errno;close(fd);return @{@"error":@"Helper unavailable — export this diagnostic and installation log",@"errno":@(code)};}
    if(!CDWrite(fd,[[command stringByAppendingString:@"\n"] dataUsingEncoding:NSUTF8StringEncoding])){close(fd);return @{@"error":@"Helper request failed"};}
    NSMutableData *data=[NSMutableData data];char b[512];
    while(data.length<8192){ssize_t n=read(fd,b,sizeof(b));if(n<=0)break;[data appendBytes:b length:n];if(memchr(b,'\n',n))break;}
    close(fd);id result=[NSJSONSerialization JSONObjectWithData:data options:0 error:NULL];
    return [result isKindOfClass:NSDictionary.class]?result:@{@"error":@"Incomplete helper reply"};
}
