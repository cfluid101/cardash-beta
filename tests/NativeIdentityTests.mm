#import "NativeIdentity.h"
#include <mach-o/loader.h>

static void Require(BOOL condition,NSString *message){if(!condition){fprintf(stderr,"%s\n",message.UTF8String);exit(1);}}
int main(int argc,char **argv){@autoreleasepool{
    if(argc==2){NSData *data=[NSData dataWithContentsOfFile:@(argv[1])];Require(data!=nil,@"retained caller missing");NSDictionary *facts=CDNativeFileIdentity(@(argv[1]));Require([facts[@"sha256"] isEqual:@"72ee56fbcd6716dd034f01c9a32f84222fdf48baae2170e0fe5d44ccdebe7064"],@"retained hash mismatch");Require([CDMachOUUID(data) isEqual:@"9517DC80-EC7F-38D1-BA2D-148CDE5FC24C"],@"retained UUID mismatch");}
    struct mach_header_64 header={};header.magic=MH_MAGIC_64;header.ncmds=1;header.sizeofcmds=sizeof(struct uuid_command);
    struct uuid_command command={};command.cmd=LC_UUID;command.cmdsize=sizeof(command);for(int i=0;i<16;i++)command.uuid[i]=(unsigned char)i;
    NSMutableData *valid=[NSMutableData dataWithBytes:&header length:sizeof(header)];[valid appendBytes:&command length:sizeof(command)];
    Require([CDMachOUUID(valid) isEqual:@"00010203-0405-0607-0809-0A0B0C0D0E0F"],@"valid UUID not decoded");
    for(NSUInteger n=0;n<valid.length;n++)Require(CDMachOUUID([valid subdataWithRange:NSMakeRange(0,n)])==nil,@"truncated header accepted");
    NSMutableData *bad=[valid mutableCopy];((struct load_command *)((char *)bad.mutableBytes+sizeof(header)))->cmdsize=0;Require(!CDMachOUUID(bad),@"zero-length command accepted");
    bad=[valid mutableCopy];((struct mach_header_64 *)bad.mutableBytes)->sizeofcmds=UINT32_MAX;Require(!CDMachOUUID(bad),@"oversized commands accepted");
    bad=[valid mutableCopy];((struct mach_header_64 *)bad.mutableBytes)->ncmds=2;Require(!CDMachOUUID(bad),@"excess commands accepted");
    bad=[valid mutableCopy];((struct mach_header_64 *)bad.mutableBytes)->sizeofcmds=sizeof(command)*2;((struct mach_header_64 *)bad.mutableBytes)->ncmds=2;[bad appendBytes:&command length:sizeof(command)];Require(!CDMachOUUID(bad),@"duplicate UUID accepted");
    NSMutableDictionary *daemon=[@{@"available":@YES,@"path":@"/System/Library/PrivateFrameworks/CarKit.framework/Support/carkitd",@"uuid":@"9517DC80-EC7F-38D1-BA2D-148CDE5FC24C",@"sha256":@"72ee56fbcd6716dd034f01c9a32f84222fdf48baae2170e0fe5d44ccdebe7064"} mutableCopy];
    NSMutableDictionary *facts=[@{@"class_image":@"/System/Library/PrivateFrameworks/CarKit.framework/CarKit",@"implementation_image":@"/System/Library/PrivateFrameworks/CarKit.framework/CarKit",@"framework_uuid":@"E7918412-DF06-3E57-9E4E-C031AD370605",@"daemon_file":daemon} mutableCopy];
    Require(CDCarKitCompletionIdentityMatches(facts),@"known evidence tuple rejected");
    for(NSString *key in @[@"class_image",@"implementation_image",@"framework_uuid"]){NSMutableDictionary *unknown=[facts mutableCopy];unknown[key]=@"unknown";Require(!CDCarKitCompletionIdentityMatches(unknown),@"unknown identity enabled typed callback");[unknown removeObjectForKey:key];Require(!CDCarKitCompletionIdentityMatches(unknown),@"missing identity enabled typed callback");}
    for(NSString *key in daemon.allKeys){NSMutableDictionary *unknown=[daemon mutableCopy];[unknown removeObjectForKey:key];facts[@"daemon_file"]=unknown;Require(!CDCarKitCompletionIdentityMatches(facts),@"missing daemon identity enabled typed callback");}
    puts("Native identity bounds and callback compatibility gates passed");return 0;
}}
