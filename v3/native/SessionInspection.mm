#import "SessionInspection.h"
#import "Common.h"
#import "NativeIdentity.h"
#import <objc/runtime.h>
#include <dlfcn.h>
#include <limits.h>
#include <mach-o/dyld.h>

static NSString *CDBoundedInspectionString(const char *value,size_t limit=1024) {
    if(!value)return @"";
    size_t count=strnlen(value,limit);
    return [[NSString alloc] initWithBytes:value length:count encoding:NSUTF8StringEncoding]?:@"";
}

static NSString *CDInspectionArchitecture(void) {
#if defined(__arm64e__)
    return @"arm64e";
#elif defined(__arm64__)
    return @"arm64";
#elif defined(__x86_64__)
    return @"x86_64";
#else
    return @"unknown";
#endif
}

static NSDictionary *CDInspectionMethod(NSString *className,NSString *selector,
                                       const char *expectedReturn,NSArray<NSString *> *expectedArguments) {
    Class cls=NSClassFromString(className);
    Method method=class_getInstanceMethod(cls,NSSelectorFromString(selector));
    NSMutableDictionary *facts=[@{@"class":className,@"selector":selector,@"available":@(method!=NULL),
        @"class_image":CDBoundedInspectionString(cls?class_getImageName(cls):NULL),
        @"encoding":@"",@"return_type":@"",@"argument_types":@[],@"argument_count":@0,
        @"arguments_truncated":@NO,@"implementation_image":@"",@"implementation_uuid":@"",
        @"matches_expected_types":@NO,@"matches_normal_owner_checks":@NO} mutableCopy];
    if(!method)return facts;
    facts[@"encoding"]=CDBoundedInspectionString(method_getTypeEncoding(method),512);
    char *returnType=method_copyReturnType(method);
    facts[@"return_type"]=CDBoundedInspectionString(returnType,256);free(returnType);
    unsigned int count=method_getNumberOfArguments(method),explicitCount=count>=2?count-2:0;
    NSMutableArray *arguments=[NSMutableArray array];
    for(unsigned int i=2;i<count&&i<18;i++){
        char *type=method_copyArgumentType(method,i);
        [arguments addObject:CDBoundedInspectionString(type,256)];free(type);
    }
    facts[@"argument_count"]=@(explicitCount);facts[@"argument_types"]=arguments;
    facts[@"arguments_truncated"]=@(explicitCount>16);
    Dl_info owner={};if(dladdr((const void *)method_getImplementation(method),&owner)){
        facts[@"implementation_image"]=CDBoundedInspectionString(owner.dli_fname);
        facts[@"implementation_uuid"]=CDLoadedImageUUID(owner.dli_fbase)?:@"";
    }
    facts[@"matches_expected_types"]=@(CDMethodMatches(cls,selector,expectedReturn,expectedArguments,NO,NO));
    facts[@"matches_normal_owner_checks"]=@(CDMethodMatches(cls,selector,expectedReturn,expectedArguments,NO,YES));
    return facts;
}

NSDictionary *CDV3InspectCarKitAtPath(NSString *frameworkPath) {
    NSMutableDictionary *framework=[@{@"path":frameworkPath,@"loaded":@NO,@"load_error":@"",
        @"image_path":@"",@"image_uuid":@""} mutableCopy];
    NSMutableDictionary *report=[@{@"schema_version":@1,@"inspection_kind":@"carkit",@"read_only":@YES,
        @"session_requested":@NO,@"complete":@NO,@"machine":CDSystem("hw.machine")?:@"",
        @"os_version":CDSystem("kern.osproductversion")?:@"",@"build":CDSystem("kern.osversion")?:@"",
        @"process_architecture":CDInspectionArchitecture(),@"framework":framework,
        @"methods":@[],@"normal_mode_method_checks_passed":@NO,@"completion_identity":@{},
        @"completion_block_abi_inferred_from_method_encoding":@NO} mutableCopy];
    @try{
        dlerror();void *handle=dlopen(frameworkPath.fileSystemRepresentation,RTLD_NOW|RTLD_LOCAL);
        framework[@"loaded"]=@(handle!=NULL);
        if(!handle)framework[@"load_error"]=CDBoundedInspectionString(dlerror());
        // Keep the image loaded until process exit: Objective-C class metadata
        // is registered globally and must not outlive its implementation image.
        if(handle){
            char resolved[PATH_MAX];
            NSString *resolvedPath=realpath(frameworkPath.fileSystemRepresentation,resolved)?CDBoundedInspectionString(resolved):frameworkPath;
            uint32_t imageCount=_dyld_image_count();
            for(uint32_t i=0;i<imageCount&&i<65536;i++){
                const char *path=_dyld_get_image_name(i);
                NSString *imagePath=CDBoundedInspectionString(path);
                if(path&&([frameworkPath isEqualToString:imagePath]||[resolvedPath isEqualToString:imagePath])){
                    framework[@"image_path"]=CDBoundedInspectionString(path);
                    framework[@"image_uuid"]=CDLoadedImageUUID(_dyld_get_image_header(i))?:@"";break;
                }
            }
        }
        NSArray *methods=@[
            CDInspectionMethod(@"CARSessionRequestHost",@"initWithDisplayName:wiredIPv6Addresses:wirelessIPv6Addresses:port:carplayWiFiUUID:deviceIdentifier:publicKey:sourceVersion:wiredCarPlaySimulator:","@",@[@"@",@"@",@"@",@"q",@"@",@"@",@"@",@"@",@"B"]),
            CDInspectionMethod(@"CARSessionRequestClient",@"startSessionWithHost:completion:","v",@[@"@",@"@?"]),
            CDInspectionMethod(@"CARSessionRequestClient",@"cancelRequests","v",@[]),
            CDInspectionMethod(@"CARSessionStatus",@"currentSession","@",@[])
        ];
        report[@"methods"]=methods;
        report[@"normal_mode_method_checks_passed"]=@([methods[0][@"matches_normal_owner_checks"] boolValue]&&
            [methods[2][@"matches_normal_owner_checks"] boolValue]&&[methods[3][@"matches_normal_owner_checks"] boolValue]);
        // @? describes a block argument, not the block's own callable ABI.
        // Preserve the existing identity gate instead of guessing that ABI.
        report[@"completion_identity"]=CDCarKitCompletionIdentity(NSClassFromString(@"CARSessionRequestClient"));
        report[@"complete"]=@YES;
    }@catch(NSException *error){
        report[@"inspection_error"]=@{@"name":CDBoundedInspectionString(error.name.UTF8String),
            @"reason":CDBoundedInspectionString(error.reason.UTF8String)};
    }
    return report;
}
