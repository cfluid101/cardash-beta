#import "HostProfile.h"
#import "Common.h"
#import "NativeIdentity.h"
#import "HostPayload.h"
#import <objc/runtime.h>
#include <dlfcn.h>
#include <cstring>

static NSString *const CarKitPath=@"/System/Library/PrivateFrameworks/CarKit.framework/CarKit";
struct DictionaryHostProfile {
    const char *uuid,*name,*referenceBuild,*artifactSHA256;
    const char *replyInvoke,*replyDescriptor,*replySignature;
    const char *architecture;
    bool mutualAuthenticationField,expandedSchema;
};
// These implementations share the inspected dictionary schema and BOOL/error
// reply ABI. An OS version alone never selects a profile. Keep each image's
// callback evidence together and require every method to belong to that image.
static const DictionaryHostProfile DictionaryProfiles[]={
    {"56E68CC1-FF26-3491-9ECA-D6974006E1A4","ios16_0_20A357_arm64e_carkit","20A357",
     "9f365d2c1981854de208960d6971699eb6692c13f632d78048c8dc8c43f62134",
     "0x1a6a70534","0x1d6a525a8","0x1a6a9d646","arm64e",false,false},
    {"8B932A1D-AFE6-32C1-A93E-FDB58CC05AE4","ios15_4_1_19E258_arm64e_carkit","19E258",
     "9bd3b17e7292a8839a49678fdc47eab22724b0e7f191633e7126b07c24f7a0fb",
     "0x198134580","0x1dc8d2dd0","0x198166676","arm64e",false,false},
    {"536A2D38-3F4E-30A3-8383-7689A7E0511D","ios15_0_19A346_arm64e_carkit","19A346",
     "a2df86f84f83d80a92f5c900d5e7fe9decb586012dfac38b76befaf9d5a6fe0d",
     "0x197a1bffc","0x1dccd4858","0x197a4de86","arm64e",false,false},
    {"AB1E14C0-03DF-38E0-ADD2-ED21A8984053","ios15_6_1_19G82_arm64e_carkit","19G82",
     "375be3677e0515217ac8f5ed6faca6cc1098619bddd5885b8ee1aa20cb17fb86",
     "0x1981fa0a8","0x1dc8a7230","0x19822c4d6","arm64e",false,false},
    {"FDACA424-7308-31BB-9444-B096D1663D17","ios16_0_20A362_arm64_carkit","20A362",
     "7eba046fafafbc033b2bd219d6c93f67c2dfde23ed7b56097415eeeef39a5218",
     "0x1a4b8e608","0x1d7fce748","0x1a4bb7676","arm64",false,false},
    {"278C602E-29BE-3065-B110-5D8635E1DB8C","ios16_6_20G75_arm64e_carkit","20G75",
     "b9865dbd8474a4d3ffcfe3f45f78a588779b4489fa51821ea48902b1a1830363",
     "0x1a8187ba4","0x1d6ea9308","0x1a81b9ce6","arm64e",true,false},
    {"755A17FE-22A6-3821-8063-EE6C3E792C9C","ios17_0_21A329_arm64e_carkit","21A329",
     "815ee557b67f9ff9fade49265f1c6308dc14b73c94d4beae6e8bbd932ad5349f",
     "0x1ac3143d8","0x1e0b23f78","0x1ac346e01","arm64e",true,true},
    {"F1329B19-1730-33F2-9B50-B4C59A0A986F","ios17_6_1_21G93_21G101_arm64e_carkit","21G93/21G101",
     "dfbdc24c32e685194c704f89c9fc20de698ac6cf267188049e6272960c9ec987",
     "0x1ad8cf7d8","0x1f1ca26e0","0x1ad90b387","arm64e",true,true},
};
static const DictionaryHostProfile *DictionaryProfileForUUID(NSString *uuid) {
    for(const auto &profile:DictionaryProfiles)if([uuid isEqual:@(profile.uuid)])return &profile;
    return nullptr;
}
static NSString *const LegacyInitializer=@"initWithDisplayName:wiredIPv6Addresses:wirelessIPv6Addresses:port:carplayWiFiUUID:deviceIdentifier:publicKey:sourceVersion:wiredCarPlaySimulator:";

#if CD_HOST_TEST
// Defined by the separately compiled fixture, never linked into the tweak.
NSDictionary *CDV3HostFixtureMethodIdentity(Class cls,SEL selector);
#endif

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
- (BOOL)supportsMutualAuthentication;
- (id)authenticationCertificateSerial;
- (id)pairedVehicleIdentifier;
- (void)startSessionWithHost:(id)host completion:(void(^)(BOOL,NSError *))completion;
- (void)startSessionWithHost:(id)host requestIdentifier:(NSUUID *)identifier completion:(void(^)(BOOL,NSError *))completion;
@end

static NSString *Bounded(const char *text) {
    if(!text)return @"";
    return [[NSString alloc] initWithBytes:text length:strnlen(text,1024) encoding:NSUTF8StringEncoding]?:@"";
}
static NSArray *HostRequirements(const DictionaryHostProfile *profile) {
    NSMutableArray *requirements=[@[@[@"initWithHostProperties:",@"@",@[@"@"],@NO],
        @[@"displayName",@"@",@[],@NO],@[@"wiredIPv6Addresses",@"@",@[],@NO],
        @[@"wirelessIPv6Addresses",@"@",@[],@NO],@[@"port",@"q",@[],@NO],
        @[@"carplayWiFiUUID",@"@",@[],@NO],@[@"deviceIdentifier",@"@",@[],@NO],
        @[@"publicKey",@"@",@[],@NO],@[@"sourceVersion",@"@",@[],@NO],
        @[@"isWiredCarPlaySimulator",@"B",@[],@NO],
        @[@"initWithCoder:",@"@",@[@"@"],@NO],@[@"encodeWithCoder:",@"v",@[@"@"],@NO],
        @[@"supportsSecureCoding",@"B",@[],@YES]] mutableCopy];
    if(profile&&profile->mutualAuthenticationField)
        [requirements addObject:@[@"supportsMutualAuthentication",@"B",@[],@NO]];
    if(profile&&profile->expandedSchema){
        [requirements addObject:@[@"authenticationCertificateSerial",@"@",@[],@NO]];
        [requirements addObject:@[@"pairedVehicleIdentifier",@"@",@[],@NO]];
    }
    return requirements;
}
static NSArray *RequestRequirement(const DictionaryHostProfile *profile) {
    return profile&&profile->expandedSchema?
        @[@"startSessionWithHost:requestIdentifier:completion:",@"v",@[@"@",@"@",@"@?"],@NO]:
        @[@"startSessionWithHost:completion:",@"v",@[@"@",@"@?"],@NO];
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
NSDictionary *CDV3HostCompletionIdentity(Class client) {
    // Preserve the established legacy evidence and identity guard verbatim.
    // Missing selectors are checked without triggering dynamic resolution.
    Method oldRequest=FindMethod(client,NSSelectorFromString(@"startSessionWithHost:completion:"),NO);
    NSMutableDictionary *facts=[CDCarKitCompletionIdentity(oldRequest?client:Nil) mutableCopy];
    if(!oldRequest){
        Method request=FindMethod(client,NSSelectorFromString(@"startSessionWithHost:requestIdentifier:completion:"),NO);
        Dl_info owner={};if(request)dladdr((const void *)method_getImplementation(request),&owner);
        facts[@"class_image"]=Bounded(client?class_getImageName(client):NULL);
        facts[@"implementation_image"]=Bounded(owner.dli_fname);
        facts[@"framework_uuid"]=CDLoadedImageUUID(owner.dli_fbase)?:@"";
        // The new request can only be enabled by its exact profile below.
        facts[@"typed_completion_enabled"]=@NO;
    }
    NSDictionary *relocated=CDNativeFileIdentity(@"/usr/libexec/carkitd");
    facts[@"daemon_candidates"]=@[facts[@"daemon_file"]?:@{},relocated];
    // This informational choice does not alter the legacy daemon guard.
    if(!oldRequest&&[relocated[@"available"] boolValue])facts[@"daemon_file"]=relocated;
    return facts;
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
    if(fixture){
        NSDictionary *facts=CDV3HostFixtureMethodIdentity(cls,selector);
        owned=method&&[facts[@"owned_by_carkit"] boolValue];uuid=facts[@"implementation_uuid"]?:@"";
    }
#else
    (void)fixture;
#endif
    return @{@"class":cls?Bounded(class_getName(cls)):@"",@"selector":spec[0],@"class_method":@(classMethod),
        @"available":@(method!=NULL),@"encoding":Bounded(method?method_getTypeEncoding(method):NULL),
        @"matches_types":@(types),@"owned_by_carkit":@(owned),@"implementation_uuid":uuid};
}
static BOOL AllDictionaryMethods(NSArray *methods,const DictionaryHostProfile *profile) {
    if(!profile)return NO;
    for(NSDictionary *method in methods)
        if(![method[@"matches_types"] boolValue]||![method[@"owned_by_carkit"] boolValue]||
           ![method[@"implementation_uuid"] isEqual:@(profile->uuid)])return NO;
    return methods.count>0;
}
static NSDictionary *Inspect(Class host,Class client,Class status,NSDictionary *context,BOOL fixture) {
    NSDictionary *legacy=context[@"legacy_completion"]?:@{};
    const DictionaryHostProfile *dictionaryProfile=DictionaryProfileForUUID(legacy[@"framework_uuid"]);
    NSMutableArray *methods=[NSMutableArray array];
    for(NSArray *spec in HostRequirements(dictionaryProfile))[methods addObject:MethodFact(host,spec,fixture)];
    [methods addObject:MethodFact(client,RequestRequirement(dictionaryProfile),fixture)];
    [methods addObject:MethodFact(client,@[@"cancelRequests",@"v",@[],@NO],fixture)];
    [methods addObject:MethodFact(status,@[@"currentSession",@"@",@[],@NO],fixture)];
    // NSObject init may legitimately be inherited; retain the established
    // Apple-owner rule for those operations rather than requiring CarKit IMPs.
    BOOL initChecks=Match(client,@"init","@",@[],NO,!fixture)&&Match(status,@"init","@",@[],NO,!fixture)&&
        Match(host,@"alloc","@",@[],YES,!fixture)&&Match(client,@"alloc","@",@[],YES,!fixture)&&Match(status,@"alloc","@",@[],YES,!fixture);
    BOOL dictionaryMethods=AllDictionaryMethods(methods,dictionaryProfile)&&initChecks;
    BOOL legacyMethods=Match(host,LegacyInitializer,"@",@[@"@",@"@",@"@",@"q",@"@",@"@",@"@",@"@",@"B"],NO,!fixture)&&
        Match(status,@"currentSession","@",@[],NO,!fixture)&&Match(client,@"cancelRequests","v",@[],NO,!fixture);
    BOOL identity=dictionaryProfile&&[legacy[@"class_image"] isEqual:CarKitPath]&&
        [legacy[@"implementation_image"] isEqual:CarKitPath];
    BOOL dictionary=identity&&dictionaryMethods;
    NSString *selected=dictionary?@(dictionaryProfile->name):
        (legacyMethods&&[legacy[@"typed_completion_enabled"] boolValue]?@"legacy_ios16_6":@"unsupported");
    NSDictionary *completion=legacy;
    if(dictionary){
        completion=@{@"typed_completion_enabled":@YES,@"basis":@"exact_framework_reply_block_descriptor_and_argument_forwarder",
            @"framework_uuid":legacy[@"framework_uuid"],@"class_image":legacy[@"class_image"],
            @"implementation_image":legacy[@"implementation_image"],@"observed_build":context[@"build"],
            @"observed_os_version":context[@"os_version"],@"inspected_architecture":@(dictionaryProfile->architecture),
            @"reference_build":@(dictionaryProfile->referenceBuild),@"build_version_used_for_selection":@NO,
            @"inspected_artifact_sha256":@(dictionaryProfile->artifactSHA256),
            @"exact_framework_implementation_inspected":@YES,@"completion_block_abi_inferred_from_method_encoding":@NO,
            @"retained_block_signature":@"v20@?0B8@\"NSError\"12",@"reply_invoke_address":@(dictionaryProfile->replyInvoke),
            @"reply_descriptor_address":@(dictionaryProfile->replyDescriptor),@"reply_signature_address":@(dictionaryProfile->replySignature),
            @"daemon_identity_used_for_callback_abi":@NO,@"daemon_implementation_inspected":@NO,
            @"daemon_file":legacy[@"daemon_file"]?:@{},@"daemon_candidates":legacy[@"daemon_candidates"]?:@[]};
    }
    NSString *diagnostic=dictionary?@"verified_host_profile":
        ([selected isEqual:@"legacy_ios16_6"]?@"retained_legacy_host_profile":
         (!dictionaryProfile?@"unknown_carkit_identity":(!identity?@"carkit_owner_mismatch":@"carkit_method_contract_mismatch")));
    return @{@"selected_profile":selected,@"dictionary_identity_matches":@(identity),
        @"request_family":dictionary&&dictionaryProfile->expandedSchema?@"host_request_identifier_completion":@"host_completion",
        @"host_schema":dictionary?(dictionaryProfile->expandedSchema?@"dictionary12":@"dictionary9"):@"legacy_or_unknown",
        @"diagnostic_code":diagnostic,@"evidence_level":dictionary?@"firmware_validated":@"retained_legacy_or_unknown",
        @"device_validation_required":@(dictionary),@"mutual_authentication_advertised":@NO,
        @"daemon_acceptance_verified":@NO,
        @"dictionary_methods_match":@(dictionaryMethods),@"legacy_method_checks_passed":@(legacyMethods),
        @"normal_mode_method_checks_passed":@(dictionary||legacyMethods),
        @"profile_matched":@(![selected isEqual:@"unsupported"]),@"methods":methods,@"completion_identity":completion};
}
NSDictionary *CDV3InspectHostProfile(Class host,Class client,Class status,NSDictionary *legacyCompletion) {
    return Inspect(host,client,status,@{@"build":CDSystem("kern.osversion")?:@"",@"os_version":CDSystem("kern.osproductversion")?:@"",
        @"legacy_completion":legacyCompletion?:@{}},NO);
}
BOOL CDV3UsesDictionaryHostProfile(NSDictionary *profile) {
    if(![profile[@"profile_matched"] boolValue])return NO;
    for(const auto &candidate:DictionaryProfiles)
        if([profile[@"selected_profile"] isEqual:@(candidate.name)])return YES;
    return NO;
}
static id Failure(NSError **error,NSInteger code,NSString *message) {
    if(error)*error=[NSError errorWithDomain:@"CarDash.V3.HostProfile" code:code userInfo:@{NSLocalizedDescriptionKey:message}];
    return nil;
}
static NSString *FieldMismatch(NSObject *host,Class cls,NSInteger port,NSString *key,const DictionaryHostProfile *profile) {
    if(!host||object_getClass(host)!=cls)return @"host class";
    id name=[host displayName],identifier=[host deviceIdentifier],publicKey=[host publicKey],version=[host sourceVersion];
    id wired=[host wiredIPv6Addresses],wireless=[host wirelessIPv6Addresses];
    if(![name isKindOfClass:NSString.class])return @"displayName type";
    if(![identifier isKindOfClass:NSString.class])return @"deviceIdentifier type";
    if(![publicKey isKindOfClass:NSString.class])return @"publicKey type (expected NSString)";
    if(![version isKindOfClass:NSString.class])return @"sourceVersion type";
    if(![wired isKindOfClass:NSArray.class]||![wireless isKindOfClass:NSArray.class])return @"address array type";
    for(id address in wired)if(![address isKindOfClass:NSString.class])return @"wired address element type";
    for(id address in wireless)if(![address isKindOfClass:NSString.class])return @"wireless address element type";
    if(profile->mutualAuthenticationField&&[host supportsMutualAuthentication])return @"supportsMutualAuthentication (receiver requires false)";
    if(profile->expandedSchema&&[host authenticationCertificateSerial]!=nil)return @"authenticationCertificateSerial (expected nil)";
    if(profile->expandedSchema&&[host pairedVehicleIdentifier]!=nil)return @"pairedVehicleIdentifier (expected nil)";
    if(![name isEqual:@"CarDash V3"])return @"displayName value";
    if(![identifier isEqual:@"02:43:44:4c:41:42"])return @"deviceIdentifier value";
    if(![publicKey isEqual:key])return @"publicKey value";
    if(![version isEqual:@"509.0"])return @"sourceVersion value";
    if(![wired isEqual:@[@"::1"]]||![wireless isEqual:@[]])return @"address array value";
    if([host carplayWiFiUUID]!=nil)return @"carplayWiFiUUID (expected nil)";
    if([host port]!=port)return @"port value";
    if(![host isWiredCarPlaySimulator])return @"wiredCarPlaySimulator value";
    return nil;
}
static id Create(Class cls,NSInteger port,NSString *key,NSError **error,BOOL fixture) {
    if(error)*error=nil;
    if(port<1024||port>65535||![key isKindOfClass:NSString.class]||key.length!=64||
       [key rangeOfCharacterFromSet:[NSCharacterSet characterSetWithCharactersInString:@"0123456789abcdef"].invertedSet].location!=NSNotFound)
        return Failure(error,1,@"Invalid host port or NSString public key");
    NSMutableArray *methods=[NSMutableArray array];
    NSDictionary *initializer=MethodFact(cls,@[@"initWithHostProperties:",@"@",@[@"@"],@NO],fixture);
    const DictionaryHostProfile *profile=DictionaryProfileForUUID(initializer[@"implementation_uuid"]);
    for(NSArray *spec in HostRequirements(profile))[methods addObject:MethodFact(cls,spec,fixture)];
    if(!AllDictionaryMethods(methods,profile)||!Match(cls,@"alloc","@",@[],YES,!fixture))
        return Failure(error,2,@"Host method type, owner or implementation identity mismatch");
    @try {
        NSMutableDictionary *properties=[@{@"displayName":@"CarDash V3",@"wiredIPAddresses":@[@"::1"],
            @"wirelessIPAddresses":@[],@"port":@(port),@"deviceID":@"02:43:44:4c:41:42",
            @"publicKey":key,@"sourceVersion":@"509.0",@"wiredCarPlaySimulator":@YES} mutableCopy];
        // This receiver does not implement the newer mutual authentication
        // protocol. Advertise that fact; nil certificate/vehicle IDs are omitted
        // as the inspected constructor permits. Never fabricate credentials.
        if(profile->expandedSchema)properties[@"supportsMutualAuth"]=@NO;
        id host=[[cls alloc] initWithHostProperties:properties];
        NSString *mismatch=FieldMismatch(host,cls,port,key,profile);
        if(mismatch)return Failure(error,3,[@"Host initialization mismatch: " stringByAppendingString:mismatch]);
        NSError *archiveError=nil;id decoded=CDSecureHostRoundTrip(host,&archiveError);
        if(!decoded){if(error)*error=archiveError;return archiveError?nil:Failure(error,4,@"Host secure-coding round trip returned nil");}
        mismatch=FieldMismatch(decoded,cls,port,key,profile);
        if(mismatch)return Failure(error,5,[@"Host secure-coding mismatch: " stringByAppendingString:mismatch]);
        return host;
    }@catch(NSException *exception){return Failure(error,6,[NSString stringWithFormat:@"Host preflight exception: %@",Bounded(exception.name.UTF8String)]);}
}
id CDV3CreateDictionaryHost(Class host,NSInteger port,NSString *key,NSError **error) {
    return Create(host,port,key,error,NO);
}
static BOOL Dispatch(id client,id host,NSDictionary *selection,void(^completion)(BOOL,NSError *),NSError **error,BOOL fixture) {
    if(error)*error=nil;
    const DictionaryHostProfile *profile=nullptr;
    for(const auto &candidate:DictionaryProfiles)
        if([selection[@"selected_profile"] isEqual:@(candidate.name)])profile=&candidate;
    BOOL legacy=[selection[@"selected_profile"] isEqual:@"legacy_ios16_6"];
    NSDictionary *identity=selection[@"completion_identity"];
    if(!client||!host||!completion||![selection[@"profile_matched"] boolValue]||
       ![identity[@"typed_completion_enabled"] boolValue]||(!profile&&!legacy)){
        Failure(error,7,@"Session request withheld: unverified host profile or callback contract");return NO;
    }
    NSDictionary *method=MethodFact(object_getClass(client),RequestRequirement(profile),fixture);
    NSString *expectedUUID=profile?@(profile->uuid):@"E7918412-DF06-3E57-9E4E-C031AD370605";
    if(![method[@"matches_types"] boolValue]||![method[@"owned_by_carkit"] boolValue]||
       ![method[@"implementation_uuid"] isEqual:expectedUUID]||![identity[@"framework_uuid"] isEqual:expectedUUID]){
        Failure(error,8,@"Session request withheld: request implementation changed after inspection");return NO;
    }
    if(profile&&profile->expandedSchema)
        [client startSessionWithHost:host requestIdentifier:[NSUUID UUID] completion:completion];
    else [client startSessionWithHost:host completion:completion];
    return YES;
}
BOOL CDV3RequestHostSession(id client,id host,NSDictionary *profile,void(^completion)(BOOL,NSError *),NSError **error) {
    return Dispatch(client,host,profile,completion,error,NO);
}
#if CD_HOST_TEST
BOOL CDV3RequestHostSessionFixture(id client,id host,NSDictionary *profile,void(^completion)(BOOL,NSError *),NSError **error) {
    return Dispatch(client,host,profile,completion,error,YES);
}
NSDictionary *CDV3FixtureHostProfile(Class host,Class client,Class status,NSDictionary *context) {
    return Inspect(host,client,status,context,YES);
}
id CDV3CreateDictionaryHostFixture(Class host,NSInteger port,NSString *key,NSError **error) {
    return Create(host,port,key,error,YES);
}
#endif
