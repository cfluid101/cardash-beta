#import "NativeIdentity.h"
#import <objc/runtime.h>
#include <mach-o/loader.h>
#include <CommonCrypto/CommonDigest.h>
#include <dlfcn.h>
#include <fcntl.h>
#include <sys/stat.h>
#include <unistd.h>

static NSString * const frameworkPath=@"/System/Library/PrivateFrameworks/CarKit.framework/CarKit";
static NSString * const daemonPath=@"/System/Library/PrivateFrameworks/CarKit.framework/Support/carkitd";

NSString *CDMachOUUID(NSData *data) {
    if(data.length<sizeof(struct mach_header_64))return nil;
    struct mach_header_64 header;memcpy(&header,data.bytes,sizeof(header));
    if(header.magic!=MH_MAGIC_64||header.sizeofcmds>1024*1024||header.ncmds>4096||header.sizeofcmds>data.length-sizeof(header))return nil;
    size_t offset=sizeof(header),end=offset+header.sizeofcmds;NSString *uuid=nil;
    for(uint32_t i=0;i<header.ncmds;i++){
        if(end-offset<sizeof(struct load_command))return nil;
        struct load_command command;memcpy(&command,(const char *)data.bytes+offset,sizeof(command));
        if(command.cmdsize<sizeof(command)||command.cmdsize>end-offset||command.cmdsize%8)return nil;
        if(command.cmd==LC_UUID){
            if(command.cmdsize!=sizeof(struct uuid_command)||uuid)return nil;
            struct uuid_command value;memcpy(&value,(const char *)data.bytes+offset,sizeof(value));
            uuid=[[NSUUID alloc] initWithUUIDBytes:value.uuid].UUIDString;
        }
        offset+=command.cmdsize;
    }
    return offset==end?uuid:nil;
}
NSString *CDLoadedImageUUID(const void *raw) {
    if(!raw)return nil;struct mach_header_64 header;memcpy(&header,raw,sizeof(header));
    // Only callers with a dyld-loaded header may use this function. The loader
    // maps its load commands; malformed/oversized metadata is still refused.
    if(header.magic!=MH_MAGIC_64||header.sizeofcmds>1024*1024||header.ncmds>4096)return nil;
    return CDMachOUUID([NSData dataWithBytes:raw length:sizeof(header)+header.sizeofcmds]);
}
NSDictionary *CDNativeFileIdentity(NSString *path) {
    int fd=open(path.fileSystemRepresentation,O_RDONLY|O_CLOEXEC|O_NOFOLLOW|O_NONBLOCK);
    if(fd<0)return @{@"path":path,@"available":@NO,@"errno":@(errno)};
    struct stat before={},after={};
    if(fstat(fd,&before)||!S_ISREG(before.st_mode)||before.st_size<=0||before.st_size>16*1024*1024){close(fd);return @{@"path":path,@"available":@NO,@"reason":@"not_regular_or_outside_size_limit"};}
    NSMutableData *data=[NSMutableData dataWithLength:(NSUInteger)before.st_size];size_t used=0;int error=0;
    while(used<data.length){ssize_t n=read(fd,(char *)data.mutableBytes+used,data.length-used);if(n<0&&errno==EINTR)continue;if(n<=0){error=n<0?errno:EIO;break;}used+=(size_t)n;}
    BOOL stable=fstat(fd,&after)==0&&before.st_size==after.st_size&&before.st_mtimespec.tv_sec==after.st_mtimespec.tv_sec&&before.st_mtimespec.tv_nsec==after.st_mtimespec.tv_nsec;close(fd);
    if(error||!stable)return @{@"path":path,@"available":@NO,@"errno":@(error),@"reason":@"read_failed_or_file_changed"};
    unsigned char digest[CC_SHA256_DIGEST_LENGTH];CC_SHA256(data.bytes,(CC_LONG)data.length,digest);NSMutableString *hex=[NSMutableString string];
    for(unsigned char byte:digest)[hex appendFormat:@"%02x",byte];
    return @{@"path":path,@"available":@YES,@"bytes":@(data.length),@"sha256":hex,@"uuid":CDMachOUUID(data)?:@""};
}
BOOL CDCarKitCompletionIdentityMatches(NSDictionary *facts) {
    NSDictionary *daemon=facts[@"daemon_file"];
    return [facts[@"class_image"] isEqual:frameworkPath]&&[facts[@"implementation_image"] isEqual:frameworkPath]&&
        [facts[@"framework_uuid"] isEqual:@"E7918412-DF06-3E57-9E4E-C031AD370605"]&&
        [daemon[@"available"] isEqual:@YES]&&[daemon[@"path"] isEqual:daemonPath]&&
        [daemon[@"uuid"] isEqual:@"9517DC80-EC7F-38D1-BA2D-148CDE5FC24C"]&&
        [daemon[@"sha256"] isEqual:@"72ee56fbcd6716dd034f01c9a32f84222fdf48baae2170e0fe5d44ccdebe7064"];
}
NSDictionary *CDCarKitCompletionIdentity(Class clientClass) {
    Method method=class_getInstanceMethod(clientClass,NSSelectorFromString(@"startSessionWithHost:completion:"));
    Dl_info owner={};if(method)dladdr((const void *)method_getImplementation(method),&owner);
    const char *classImage=clientClass?class_getImageName(clientClass):NULL;
    NSMutableDictionary *facts=[@{@"class_image":classImage?@(classImage):@"",@"implementation_image":owner.dli_fname?@(owner.dli_fname):@"",
        @"framework_uuid":CDLoadedImageUUID(owner.dli_fbase)?:@"",@"daemon_file":CDNativeFileIdentity(daemonPath),
        @"basis":@"retained_caller_block_signature_and_historical_path_matched_framework_uuid",
        @"retained_block_signature":@"v20@?0B8@\"NSError\"12",@"exact_framework_implementation_inspected":@NO} mutableCopy];
    facts[@"typed_completion_enabled"]=@(CDCarKitCompletionIdentityMatches(facts));return facts;
}
