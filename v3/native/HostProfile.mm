#import "HostProfile.h"
#import "Common.h"
#import "NativeIdentity.h"
#import "HostPayload.h"
#import <objc/runtime.h>
#include <dlfcn.h>
#include <cstring>

static NSString *const CarKitPath=@"/System/Library/PrivateFrameworks/CarKit.framework/CarKit";
static NSString *const DictionaryUUID=@"56E68CC1-FF26-3491-9ECA-D6974006E1A4";
static NSString *const DictionaryProfile=@"ios16_0_20A357_arm64e_carkit";
static NSString *const LegacyInitializer=@"initWithDisplayName:wiredIPv6Addresses:wirelessIPv6Addresses:port:carplayWiFiUUID:deviceIdentifier:publicKey:sourceVersion:wiredCarPlaySimulator:";

@interface NSObject (CDV3DictionaryHost)
- (id)initWithHostProperties:(id)properties;
- (id)displayName;
- (id)wiredIPv6Addresses;
- (id)wirelessIPv6Addresses;
- (long long)port;
- (id)carplayWiFiUUID;
- (id)deviceIdentifier;
- (id)publicKey;
- (id)sourceVersion;
- (BOOL)isWiredCarPlaySimulator;
@end

static NSString *Bounded(const char *text) {
    if(!text)return @"";
    return [[NSString alloc] initWithBytes:text length:strnlen(text,1024) encoding:NSUTF8StringEncoding]?:@"";
}
static NSArray *HostRequirements(void) {
    return @[@[@"initWithHostProperties:",@"@",@[@"@"],@NO],
        @[@"displayName",@"@",@[],@NO],@[@"wiredIPv6Addresses",@"@",@[],@NO],
        @[@"wirelessIPv6Addresses",@"@",@[],@NO],@[@"port",@"q",@[],@NO],
        @[@"carplayWiFiUUID",@"@",@[],@NO],@[@"deviceIdentifier",@"@",@[],@NO],
        @[@"publicKey",@"@",@[],@NO],@[@"sourceVersion",@"@",@[],@NO],
        @[@"isWiredCarPlaySimulator",@"B",@[],@NO],
        @[@"initWithCoder:",@"@",@[@"@"],@NO],@[@"encodeWithCoder:",@"v",@[@"@"],@NO],
        @[@"supportsSecureCoding",@"B",@[],@YES]];
}
static Method FindMethod(Class cls,SEL selector,BOOL classMethod) {
    // class_getInstanceMethod can trigger dynamic method resolution for a
    // missing selector. Inventory the lists directly to keep inspection inert.
    Class current=classMethod?object_getClass(cls):cls;
    for(unsigned depth=0;current&&depth<32;depth++,current=class_getSuperclass(current)){
        unsigned count=0;Method *methods=class_copyMethodList(current,&count);Method found=NULL;
        for(unsigned i=0;i<count;i++)if(method_getName(methods[i])==selector){found=methods[i];break;}
        free(methods);if(found)return found;
    }return NULL;
}
static BOOL Match(Class cls,NSString *selector,const char *result,NSArray *args,BOOL classMethod,BOOL owner) {
    return FindMethod(cls,NSSelectorFromString(selector),classMethod)&&CDMethodMatches(cls,selector,result,args,classMethod,owner);
}
static NSDictionary *MethodFact(Class cls,NSArray *spec,BOOL fixture) {
    BOOL classMethod=[spec[3] boolValue];SEL selector=NSSelectorFromString(spec[0]);
    Method method=FindMethod(cls,selector,classMethod);
    Dl_info owner={};if(method)dladdr((const void *)method_getImplementation(method),&owner);
    NSString *image=Bounded(owner.dli_fname),*uuid=CDLoadedImageUUID(owner.dli_fbase)?:@"";
    BOOL types=method&&CDMethodMatches(cls,spec[0],[spec[1] UTF8String],spec[2],classMethod,NO);
    BOOL owned=[image isEqual:CarKitPath]&&[Bounded(cls?class_getImageName(cls):NULL) isEqual:CarKitPath];
#if CD_HOST_TEST
    if(fixture){owned=method!=NULL;uuid=DictionaryUUID;}
#else
    (void)fixture;
#endif
    return @{@"class":cls?Bounded(class_getName(cls)):@"",@"selector":spec[0],@"class_method":@(classMethod),
        @"available":@(method!=NULL),@"encoding":Bounded(method?method_getTypeEncoding(method):NULL),
        @"matches_types":@(types),@"owned_by_carkit":@(owned),@"implementation_uuid":uuid};
}
static BOOL AllDictionaryMethods(NSArray *methods) {
    for(NSDictionary *method in methods)
        if(![method[@"matches_types"] boolValue]||![method[@"owned_by_carkit"] boolValue]||
           ![method[@"implementation_uuid"] isEqual:DictionaryUUID])return NO;
    return methods.count>0;
}
static NSDictionary *Inspect(Class host,Class client,Class status,NSDictionary *context,BOOL fixture) {
    NSMutableArray *methods=[NSMutableArray array];
    for(NSArray *spec in HostRequirements())[methods addObject:MethodFact(host,spec,fixture)];
    for(NSArray *spec in @[@[@"startSessionWithHost:completion:",@"v",@[@"@",@"@?"],@NO],
                           @[@"cancelRequests",@"v",@[],@NO]])[methods addObject:MethodFact(client,spec,fixture)];
    [methods addObject:MethodFact(status,@[@"currentSession",@"@",@[],@NO],fixture)];
    // NSObject init may legitimately be inherited; retain the established
    // Apple-owner rule for those operations rather than requiring CarKit IMPs.
    BOOL initChecks=Match(client,@"init","@",@[],NO,!fixture)&&Match(status,@"init","@",@[],NO,!fixture)&&
        Match(host,@"alloc","@",@[],YES,!fixture)&&Match(client,@"alloc","@",@[],YES,!fixture)&&Match(status,@"alloc","@",@[],YES,!fixture);
    BOOL dictionaryMethods=AllDictionaryMethods(methods)&&initChecks;
    NSDictionary *legacy=context[@"legacy_completion"]?:@{};
    BOOL legacyMethods=Match(host,LegacyInitializer,"@",@[@"@",@"@",@"@",@"q",@"@",@"@",@"@",@"@",@"B"],NO,!fixture)&&
        Match(status,@"currentSession","@",@[],NO,!fixture)&&Match(client,@"cancelRequests","v",@[],NO,!fixture);
    BOOL identity=[legacy[@"framework_uuid"] isEqual:DictionaryUUID]&&[legacy[@"class_image"] isEqual:CarKitPath]&&
        [legacy[@"implementation_image"] isEqual:CarKitPath];
    BOOL dictionary=identity&&dictionaryMethods;
    NSString *selected=dictionary?DictionaryProfile:
        (legacyMethods&&[legacy[@"typed_completion_enabled"] boolValue]?@"legacy_ios16_6":@"unsupported");
    NSDictionary *completion=legacy;
    if(dictionary){
        completion=@{@"typed_completion_enabled":@YES,@"basis":@"exact_framework_reply_block_descriptor_and_argument_forwarder",
            @"framework_uuid":legacy[@"framework_uuid"],@"class_image":legacy[@"class_image"],
            @"implementation_image":legacy[@"implementation_image"],@"observed_build":context[@"build"],
            @"observed_os_version":context[@"os_version"],@"inspected_architecture":@"arm64e",
            @"reference_build":@"20A357",@"build_version_used_for_selection":@NO,
            @"inspected_artifact_sha256":@"9f365d2c1981854de208960d6971699eb6692c13f632d78048c8dc8c43f62134",
            @"exact_framework_implementation_inspected":@YES,@"completion_block_abi_inferred_from_method_encoding":@NO,
            @"retained_block_signature":@"v20@?0B8@\"NSError\"12",@"reply_invoke_address":@"0x1a6a70534",
            @"reply_descriptor_address":@"0x1d6a525a8",@"reply_signature_address":@"0x1a6a9d646",
            @"daemon_identity_used_for_callback_abi":@NO,@"daemon_implementation_inspected":@NO,
            @"daemon_file":legacy[@"daemon_file"]?:@{}};
    }
    return @{@"selected_profile":selected,@"dictionary_identity_matches":@(identity),
        @"dictionary_methods_match":@(dictionaryMethods),@"legacy_method_checks_passed":@(legacyMethods),
        @"normal_mode_method_checks_passed":@(dictionary||legacyMethods),
        @"profile_matched":@(![selected isEqual:@"unsupported"]),@"methods":methods,@"completion_identity":completion};
}
NSDictionary *CDV3InspectHostProfile(Class host,Class client,Class status,NSDictionary *legacyCompletion) {
    return Inspect(host,client,status,@{@"build":CDSystem("kern.osversion")?:@"",@"os_version":CDSystem("kern.osproductversion")?:@"",
        @"legacy_completion":legacyCompletion?:@{}},NO);
}
BOOL CDV3UsesDictionaryHostProfile(NSDictionary *profile) {
    return [profile[@"selected_profile"] isEqual:DictionaryProfile]&&[profile[@"profile_matched"] boolValue];
}
static id Failure(NSError **error,NSInteger code,NSString *message) {
    if(error)*error=[NSError errorWithDomain:@"CarDash.V3.HostProfile" code:code userInfo:@{NSLocalizedDescriptionKey:message}];
    return nil;
}
static BOOL FieldsMatch(NSObject *host,Class cls,NSInteger port,NSString *key) {
    if(!host||object_getClass(host)!=cls)return NO;
    id name=[host displayName],identifier=[host deviceIdentifier],publicKey=[host publicKey],version=[host sourceVersion];
    id wired=[host wiredIPv6Addresses],wireless=[host wirelessIPv6Addresses];
    if(![name isKindOfClass:NSString.class]||![identifier isKindOfClass:NSString.class]||
       ![publicKey isKindOfClass:NSString.class]||![version isKindOfClass:NSString.class]||
       ![wired isKindOfClass:NSArray.class]||![wireless isKindOfClass:NSArray.class])return NO;
    for(id address in wired)if(![address isKindOfClass:NSString.class])return NO;
    for(id address in wireless)if(![address isKindOfClass:NSString.class])return NO;
    return [name isEqual:@"CarDash V3"]&&[identifier isEqual:@"02:43:44:4c:41:42"]&&[publicKey isEqual:key]&&
        [version isEqual:@"509.0"]&&[wired isEqual:@[@"::1"]]&&[wireless isEqual:@[]]&&[host carplayWiFiUUID]==nil&&
        [host port]==port&&[host isWiredCarPlaySimulator];
}
static id Create(Class cls,NSInteger port,NSString *key,NSError **error,BOOL fixture) {
    if(error)*error=nil;
    if(port<1024||port>65535||![key isKindOfClass:NSString.class]||key.length!=64||
       [key rangeOfCharacterFromSet:[NSCharacterSet characterSetWithCharactersInString:@"0123456789abcdef"].invertedSet].location!=NSNotFound)
        return Failure(error,1,@"Invalid host port or NSString public key");
    NSMutableArray *methods=[NSMutableArray array];
    for(NSArray *spec in HostRequirements())[methods addObject:MethodFact(cls,spec,fixture)];
    if(!AllDictionaryMethods(methods)||!Match(cls,@"alloc","@",@[],YES,!fixture))
        return Failure(error,2,@"Host method type, owner or implementation identity mismatch");
    @try {
        NSDictionary *properties=@{@"displayName":@"CarDash V3",@"wiredIPAddresses":@[@"::1"],
            @"wirelessIPAddresses":@[],@"port":@(port),@"deviceID":@"02:43:44:4c:41:42",
            @"publicKey":key,@"sourceVersion":@"509.0",@"wiredCarPlaySimulator":@YES};
        id host=[[cls alloc] initWithHostProperties:properties];
        if(!FieldsMatch(host,cls,port,key))return Failure(error,3,@"Host fields did not match after dictionary initialization");
        NSError *archiveError=nil;id decoded=CDSecureHostRoundTrip(host,&archiveError);
        if(!decoded){if(error)*error=archiveError;return archiveError?nil:Failure(error,4,@"Host secure-coding round trip returned nil");}
        if(!FieldsMatch(decoded,cls,port,key))return Failure(error,5,@"Host fields did not survive secure coding");
        return host;
    }@catch(NSException *exception){return Failure(error,6,[NSString stringWithFormat:@"Host preflight exception: %@",Bounded(exception.name.UTF8String)]);}
}
id CDV3CreateDictionaryHost(Class host,NSInteger port,NSString *key,NSError **error) {
    return Create(host,port,key,error,NO);
}
#if CD_HOST_TEST
NSDictionary *CDV3FixtureHostProfile(Class host,Class client,Class status,NSDictionary *context) {
    return Inspect(host,client,status,context,YES);
}
id CDV3CreateDictionaryHostFixture(Class host,NSInteger port,NSString *key,NSError **error) {
    return Create(host,port,key,error,YES);
}
#endif
