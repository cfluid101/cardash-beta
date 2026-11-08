#import "ServiceEnvironment.h"
#include <sys/stat.h>
#include <sys/sysctl.h>
#include <unistd.h>
#include <errno.h>
#include <stdlib.h>
#include <string.h>

static NSString *SystemValue(const char *name) {
 size_t size=0;if(sysctlbyname(name,nullptr,&size,nullptr,0)||!size||size>4096)return @"";
 NSMutableData *data=[NSMutableData dataWithLength:size];
 if(sysctlbyname(name,data.mutableBytes,&size,nullptr,0))return @"";
 return [[NSString alloc] initWithBytes:data.bytes length:strnlen((const char *)data.bytes,MIN(size,data.length)) encoding:NSUTF8StringEncoding]?:@"";
}
static NSDictionary *PathCheck(NSString *path) {
 struct stat st={};int result=lstat(path.fileSystemRepresentation,&st);int code=result?errno:0;
 NSString *type=result?(code==ENOENT||code==ENOTDIR?@"missing":@"unavailable"):S_ISDIR(st.st_mode)?@"directory":S_ISREG(st.st_mode)?@"file":S_ISSOCK(st.st_mode)?@"socket":S_ISLNK(st.st_mode)?@"symlink":@"other";
 NSMutableDictionary *value=[@{@"path":path,@"exists":@(result==0),@"errno":@(code),@"type":type} mutableCopy];
 if(!result){value[@"uid"]=@(st.st_uid);value[@"gid"]=@(st.st_gid);value[@"mode"]=@(st.st_mode&07777);value[@"readable"]=@(access(path.fileSystemRepresentation,R_OK)==0);value[@"executable"]=@(access(path.fileSystemRepresentation,X_OK)==0);}
 return value;
}
static NSDictionary *Context(NSString *root,NSString *source,NSString *executable,NSString *version,NSString *rootError) {
 NSString *state=[root stringByAppendingPathComponent:@"var/lib/cardash-v3"];
 NSMutableArray *checks=[NSMutableArray array];
 for(NSString *relative in @[@"var/lib/cardash-v3",@"var/lib/cardash-v3/control.sock",@"usr/bin/python3",@"usr/libexec/cardash-v3-service",@"usr/lib/cardash-v3/backend/server.py",@"usr/lib/libcrypto.3.dylib",@"Library/LaunchDaemons/com.cfluid.cardash.v3.plist"]){[checks addObject:PathCheck([root stringByAppendingPathComponent:relative])];}
 [checks addObject:PathCheck([executable.stringByDeletingLastPathComponent stringByAppendingPathComponent:@".jbroot"])];
 return @{@"packageVersion":version?:@"",@"machine":SystemValue("hw.machine"),@"osVersion":SystemValue("kern.osproductversion"),@"build":SystemValue("kern.osversion"),@"uid":@(getuid()),@"euid":@(geteuid()),@"gid":@(getgid()),@"appPath":executable.stringByDeletingLastPathComponent?:@"",@"executablePath":executable?:@"",@"socketPath":[state stringByAppendingPathComponent:@"control.sock"],@"stateDirectory":state,@"rootPath":root,@"rootSource":source,@"rootError":rootError?:@"",@"pathChecks":checks};
}
NSArray<NSDictionary *> *CDV3DiagnosticContexts(NSString *executablePath, NSString *packageVersion) {
 // Discovery is for an exported report only. It never changes service paths,
 // launches another daemon, or scans unrelated applications/containers.
 NSString *link=[executablePath.stringByDeletingLastPathComponent stringByAppendingPathComponent:@".jbroot"];
 NSString *resolved=nil,*error=@"";struct stat st={};
 if(lstat(link.fileSystemRepresentation,&st)){int code=errno;error=[NSString stringWithFormat:@"Executable .jbroot link unavailable (%d: %s)",code,strerror(code)];}
 else if(!S_ISLNK(st.st_mode))error=@"Executable .jbroot entry is not a symbolic link";
 else {
  char *path=realpath(link.fileSystemRepresentation,nullptr);
  if(!path){int code=errno;error=[NSString stringWithFormat:@"Executable .jbroot link cannot resolve (%d: %s)",code,strerror(code)];}
  else {
   if(!stat(path,&st)&&S_ISDIR(st.st_mode))resolved=@(path);
   else error=@"Executable .jbroot link does not resolve to a directory";
   free(path);
  }
 }
 NSMutableArray *contexts=[NSMutableArray arrayWithObject:Context(@"/var/jb",@"configured-rootless",executablePath,packageVersion,error)];
 if(resolved&&![resolved isEqual:@"/var/jb"])[contexts addObject:Context(resolved,@"executable-jbroot-link",executablePath,packageVersion,@"")];
 return contexts;
}
