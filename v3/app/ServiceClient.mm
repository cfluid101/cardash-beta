#import "ServiceClient.h"
#include <sys/socket.h>
#include <sys/un.h>
#include <unistd.h>
#include <errno.h>
#include <string.h>

static NSString *ErrorName(int code) {
 switch(code) {
  case ENOENT:return @"ENOENT";case ECONNREFUSED:return @"ECONNREFUSED";
  case EACCES:return @"EACCES";case EPERM:return @"EPERM";
  case ENAMETOOLONG:return @"ENAMETOOLONG";case EPROTO:return @"EPROTO";
  case ECONNRESET:return @"ECONNRESET";case EAGAIN:return @"EAGAIN";
  case ETIMEDOUT:return @"ETIMEDOUT";case EMSGSIZE:return @"EMSGSIZE";
  case EINVAL:return @"EINVAL";default:return [NSString stringWithFormat:@"errno_%d",code];
 }
}
static NSDictionary *Failure(NSString *stage,int code,NSString *path) {
 NSString *name=ErrorName(code);
 return @{@"ok":@NO,@"error":[NSString stringWithFormat:@"V3 service connection failed (%@: %s). Tap Export diagnostic report to share startup details.",name,strerror(code)],@"errno":@(code),@"errnoName":name,@"stage":stage,@"socketPath":path?:@""};
}
NSDictionary *CDV3ServiceRequest(NSString *action, NSString *socketPath) {
 sockaddr_un addr={};addr.sun_family=AF_UNIX;
 NSData *pathData=[socketPath dataUsingEncoding:NSUTF8StringEncoding];
 if(!pathData.length||memchr(pathData.bytes,0,pathData.length))return Failure(@"address",EINVAL,socketPath);
 if(pathData.length>=sizeof(addr.sun_path))return Failure(@"address",ENAMETOOLONG,socketPath);
 memcpy(addr.sun_path,pathData.bytes,pathData.length);
 int fd=socket(AF_UNIX,SOCK_STREAM,0);
 if(fd<0)return Failure(@"socket",errno,socketPath);
 timeval timeout={15,0};int one=1;
 if(setsockopt(fd,SOL_SOCKET,SO_RCVTIMEO,&timeout,sizeof(timeout))||setsockopt(fd,SOL_SOCKET,SO_SNDTIMEO,&timeout,sizeof(timeout))||setsockopt(fd,SOL_SOCKET,SO_NOSIGPIPE,&one,sizeof(one))) {
  int code=errno;close(fd);return Failure(@"configure",code,socketPath);
 }
 if(connect(fd,(sockaddr*)&addr,sizeof(addr))) {
  int code=errno;close(fd);return Failure(@"connect",code,socketPath);
 }
 NSData *json=[NSJSONSerialization dataWithJSONObject:@{@"action":action?:@""} options:0 error:nil];
 NSMutableData *wire=[json mutableCopy];[wire appendBytes:"\n" length:1];NSUInteger sent=0;
 while(sent<wire.length) {
  ssize_t n=send(fd,(const char *)wire.bytes+sent,wire.length-sent,0);
  if(n<0&&errno==EINTR)continue;
  if(n<=0){int code=n<0?errno:ECONNRESET;close(fd);return Failure(@"send",code,socketPath);}
  sent+=(NSUInteger)n;
 }
 const NSUInteger limit=5*1024*1024;NSMutableData *received=[NSMutableData data];char buf[8192];BOOL complete=NO;
 while(received.length<limit) {
  ssize_t n=recv(fd,buf,MIN(sizeof(buf),limit-received.length),0);
  if(n<0&&errno==EINTR)continue;
  if(n<=0){int code=n<0?errno:ECONNRESET;close(fd);return Failure(@"receive",code,socketPath);}
  [received appendBytes:buf length:(NSUInteger)n];
  if(memchr(buf,'\n',(size_t)n)){complete=YES;break;}
 }
 close(fd);
 if(!complete)return Failure(@"response",EMSGSIZE,socketPath);
 id value=[NSJSONSerialization JSONObjectWithData:received options:0 error:nil];
 if(![value isKindOfClass:NSDictionary.class])return Failure(@"response",EPROTO,socketPath);
 return value;
}
