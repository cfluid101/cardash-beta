#import "HostProfile.h"
#import <objc/runtime.h>
#include <unistd.h>

static NSString *Mode;
static NSString *FixtureUUID;
static NSUInteger Initializations;
static NSUInteger Encodings;
static NSUInteger Decodings;
static BOOL MutualField,ExpandedSchema;
static NSString *ExpectedInvoke;
static unsigned OldRequests,NewRequests;
static void Require(BOOL value,const char *message){if(!value){fprintf(stderr,"%s\n",message);exit(1);}}

// Only image identity is substituted: runtime methods, type checks, host
// construction and secure archiving below are real. Production builds never
// link this provider. Mixed-image fixtures catch accepting any known UUID
// independently rather than requiring one consistent inspected image.
NSDictionary *CDV3HostFixtureMethodIdentity(Class cls,SEL selector) {
    (void)cls;
    NSString *uuid=FixtureUUID;BOOL owned=YES;
    if(selector==@selector(port)){
        if([Mode containsString:@"mixed-method-uuid"])
            uuid=[FixtureUUID isEqual:@"8B932A1D-AFE6-32C1-A93E-FDB58CC05AE4"]?
                @"56E68CC1-FF26-3491-9ECA-D6974006E1A4":@"8B932A1D-AFE6-32C1-A93E-FDB58CC05AE4";
        if([Mode containsString:@"unknown-method-uuid"])uuid=@"UNKNOWN";
        if([Mode containsString:@"foreign-method-owner"])owned=NO;
    }
    return @{@"implementation_uuid":uuid,@"owned_by_carkit":@(owned)};
}

@interface CDHost16:NSObject<NSSecureCoding>
@property(nonatomic,copy) NSString *displayName;
@property(nonatomic,copy) NSArray *wiredIPv6Addresses;
@property(nonatomic,copy) NSArray *wirelessIPv6Addresses;
@property(nonatomic) long long port;
@property(nonatomic,copy) NSString *carplayWiFiUUID;
@property(nonatomic,copy) NSString *deviceIdentifier;
@property(nonatomic,strong) id publicKey;
@property(nonatomic,copy) NSString *sourceVersion;
@property(nonatomic,getter=isWiredCarPlaySimulator) bool wiredCarPlaySimulator;
@property(nonatomic) bool supportsMutualAuthentication;
@property(nonatomic,copy) NSData *authenticationCertificateSerial;
@property(nonatomic,copy) NSUUID *pairedVehicleIdentifier;
- (id)initWithHostProperties:(NSDictionary *)properties;
@end
@implementation CDHost16
// macOS Intel BOOL is char; this private iOS ABI encodes BOOL as B.
#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Wmismatched-return-types"
+(bool)supportsSecureCoding{return ![Mode isEqual:@"secure-disabled"];}
#pragma clang diagnostic pop
-(id)initWithHostProperties:(NSDictionary *)p {
    Initializations++;
    Require(p.count==(ExpandedSchema?9:8),"Unexpected dictionary key count");
    Require(!p[@"authenticationCertificateSerial"]&&!p[@"pairedVehicleIdentifier"],"Nil identity fields must be omitted");
    if(ExpandedSchema)Require([p[@"supportsMutualAuth"] isEqual:@NO],"Mutual authentication not explicitly disabled");
    else Require(!p[@"supportsMutualAuth"],"Old schema received new key");
    Require([p[@"wiredIPAddresses"] isEqual:@[@"::1"]]&&[p[@"wirelessIPAddresses"] isEqual:@[]],"Wrong address dictionary keys");
    Require([p[@"deviceID"] isEqual:@"02:43:44:4c:41:42"],"Wrong identity dictionary key");
    Require(!p[@"wiredIPv6Addresses"]&&!p[@"deviceIdentifier"]&&!p[@"carplayWiFiUUID"],"Accessor key or nil sentinel sent");
    if((self=[super init])){
        _displayName=p[@"displayName"];_wiredIPv6Addresses=p[@"wiredIPAddresses"];
        _wirelessIPv6Addresses=p[@"wirelessIPAddresses"];_port=[p[@"port"] longLongValue];
        _deviceIdentifier=p[@"deviceID"];_publicKey=p[@"publicKey"];
        _sourceVersion=p[@"sourceVersion"];_wiredCarPlaySimulator=[p[@"wiredCarPlaySimulator"] boolValue];
        if(ExpandedSchema){_supportsMutualAuthentication=[p[@"supportsMutualAuth"] boolValue];
            _authenticationCertificateSerial=p[@"authenticationCertificateSerial"];_pairedVehicleIdentifier=p[@"pairedVehicleIdentifier"];}
        if([Mode isEqual:@"mutual-live"])_supportsMutualAuthentication=true;
        if([Mode isEqual:@"serial-live"])_authenticationCertificateSerial=[NSData data];
        if([Mode isEqual:@"vehicle-live"])_pairedVehicleIdentifier=[NSUUID UUID];
        if([Mode isEqual:@"corrupt-live"])_deviceIdentifier=@"another host";
        if([Mode isEqual:@"wrong-live-type"])_publicKey=[_publicKey dataUsingEncoding:NSUTF8StringEncoding];
    }return self;
}
-(void)encodeWithCoder:(NSCoder *)coder {
    Encodings++;
    if([Mode isEqual:@"archive-throws"])@throw [NSException exceptionWithName:@"FixtureArchiveFailure" reason:@"test" userInfo:nil];
    [coder encodeObject:self.displayName forKey:@"displayName"];
    [coder encodeObject:self.wiredIPv6Addresses forKey:@"wiredIPAddresses"];
    [coder encodeObject:self.wirelessIPv6Addresses forKey:@"wirelessIPAddresses"];
    [coder encodeInteger:self.port forKey:@"port"];
    [coder encodeObject:self.deviceIdentifier forKey:@"deviceID"];
    [coder encodeObject:self.publicKey forKey:@"publicKey"];
    [coder encodeObject:self.sourceVersion forKey:@"sourceVersion"];
    [coder encodeObject:@(self.wiredCarPlaySimulator) forKey:@"wiredCarPlaySimulator"];
    if(ExpandedSchema){
        [coder encodeObject:@(self.supportsMutualAuthentication) forKey:@"supportsMutualAuth"];
        if(self.authenticationCertificateSerial)[coder encodeObject:self.authenticationCertificateSerial forKey:@"authenticationCertificateSerial"];
        if(self.pairedVehicleIdentifier)[coder encodeObject:self.pairedVehicleIdentifier forKey:@"pairedVehicleIdentifier"];
    }
}
-(id)initWithCoder:(NSCoder *)coder {
    Decodings++;
    if((self=[super init])){
        NSSet *arrays=[NSSet setWithObjects:NSArray.class,NSString.class,nil];
        _displayName=[coder decodeObjectOfClass:NSString.class forKey:@"displayName"];
        _wiredIPv6Addresses=[coder decodeObjectOfClasses:arrays forKey:@"wiredIPAddresses"];
        _wirelessIPv6Addresses=[coder decodeObjectOfClasses:arrays forKey:@"wirelessIPAddresses"];
        _port=[coder decodeIntegerForKey:@"port"];
        _deviceIdentifier=[coder decodeObjectOfClass:NSString.class forKey:@"deviceID"];
        _publicKey=[coder decodeObjectOfClass:NSString.class forKey:@"publicKey"];
        _sourceVersion=[coder decodeObjectOfClass:NSString.class forKey:@"sourceVersion"];
        _wiredCarPlaySimulator=[[coder decodeObjectOfClass:NSNumber.class forKey:@"wiredCarPlaySimulator"] boolValue];
        if(ExpandedSchema){
            _supportsMutualAuthentication=[[coder decodeObjectOfClass:NSNumber.class forKey:@"supportsMutualAuth"] boolValue];
            if([coder containsValueForKey:@"authenticationCertificateSerial"])_authenticationCertificateSerial=[coder decodeObjectOfClass:NSData.class forKey:@"authenticationCertificateSerial"];
            if([coder containsValueForKey:@"pairedVehicleIdentifier"])_pairedVehicleIdentifier=[coder decodeObjectOfClass:NSUUID.class forKey:@"pairedVehicleIdentifier"];
        }
        if([Mode isEqual:@"mutual-wire"])_supportsMutualAuthentication=true;
        if([Mode isEqual:@"serial-wire"])_authenticationCertificateSerial=[NSData data];
        if([Mode isEqual:@"vehicle-wire"])_pairedVehicleIdentifier=[NSUUID UUID];
        if([Mode isEqual:@"corrupt-wire"])_port++;
        if([Mode isEqual:@"wrong-wire-type"])_publicKey=[_publicKey dataUsingEncoding:NSUTF8StringEncoding];
    }return self;
}
@end

@interface CDLegacyHost:NSObject @end
@implementation CDLegacyHost
+(void)initialize{_exit(91);}
-(id)initWithDisplayName:(id)n wiredIPv6Addresses:(id)w wirelessIPv6Addresses:(id)r port:(long long)p carplayWiFiUUID:(id)u deviceIdentifier:(id)i publicKey:(id)k sourceVersion:(id)v wiredCarPlaySimulator:(bool)s{_exit(92);}
@end
@interface CDClient:NSObject @end
@implementation CDClient
+(void)initialize{_exit(93);}
-(void)startSessionWithHost:(id)host completion:(void(^)(BOOL,NSError *))completion{_exit(94);}
-(void)cancelRequests{_exit(95);}
@end
@interface CDClient17:NSObject @end
@implementation CDClient17
+(void)initialize{_exit(93);}
-(void)startSessionWithHost:(id)host requestIdentifier:(NSUUID *)identifier completion:(void(^)(BOOL,NSError *))completion{_exit(94);}
-(void)cancelRequests{_exit(95);}
@end
@interface CDStatus:NSObject @end
@implementation CDStatus
+(void)initialize{_exit(96);}
-(id)currentSession{_exit(97);}
@end

@interface CDDispatchClient:NSObject @end
@implementation CDDispatchClient
-(void)startSessionWithHost:(id)host completion:(void(^)(BOOL,NSError *))completion{
    Require(host!=nil,"Missing old request host");OldRequests++;
    completion(YES,[NSError errorWithDomain:@"Fixture.Native" code:42 userInfo:nil]);
}
-(void)startSessionWithHost:(id)host requestIdentifier:(NSUUID *)identifier completion:(void(^)(BOOL,NSError *))completion{
    Require(host!=nil&&[identifier isKindOfClass:NSUUID.class],"New request requires actual NSUUID");NewRequests++;
    completion(NO,[NSError errorWithDomain:@"Fixture.Native" code:43 userInfo:nil]);
}
@end

static NSDictionary *Context(NSString *uuid,NSString *build,BOOL legacy) {
    NSString *path=@"/System/Library/PrivateFrameworks/CarKit.framework/CarKit";
    return @{@"build":build,@"os_version":@"16.0",@"legacy_completion":@{
        @"framework_uuid":uuid,@"class_image":path,@"implementation_image":path,
        @"typed_completion_enabled":@(legacy),@"basis":@"retained_legacy_basis",
        @"daemon_file":@{@"available":@NO}}};
}
static id WrongMethod(id self,SEL selector){(void)self;(void)selector;_exit(98);}
int main(int argc,char **argv){@autoreleasepool{
    Require(argc==2,"Missing mode");Mode=@(argv[1]);
    NSArray *profiles=@[
        @[@"-ios15",@"8B932A1D-AFE6-32C1-A93E-FDB58CC05AE4",@"19E258",@"ios15_4_1_19E258_arm64e_carkit",@"0x198134580",@NO,@NO],
        @[@"-15early",@"536A2D38-3F4E-30A3-8383-7689A7E0511D",@"19A346",@"ios15_0_19A346_arm64e_carkit",@"0x197a1bffc",@NO,@NO],
        @[@"-15late",@"AB1E14C0-03DF-38E0-ADD2-ED21A8984053",@"19G82",@"ios15_6_1_19G82_arm64e_carkit",@"0x1981fa0a8",@NO,@NO],
        @[@"-16arm64",@"FDACA424-7308-31BB-9444-B096D1663D17",@"20A362",@"ios16_0_20A362_arm64_carkit",@"0x1a4b8e608",@NO,@NO],
        @[@"-16arm64e",@"278C602E-29BE-3065-B110-5D8635E1DB8C",@"20G75",@"ios16_6_20G75_arm64e_carkit",@"0x1a8187ba4",@YES,@NO],
        @[@"-17early",@"755A17FE-22A6-3821-8063-EE6C3E792C9C",@"21A329",@"ios17_0_21A329_arm64e_carkit",@"0x1ac3143d8",@YES,@YES],
        @[@"-17late",@"F1329B19-1730-33F2-9B50-B4C59A0A986F",@"21G93/21G101",@"ios17_6_1_21G93_21G101_arm64e_carkit",@"0x1ad8cf7d8",@YES,@YES]];
    NSArray *selected=@[@"",@"56E68CC1-FF26-3491-9ECA-D6974006E1A4",@"20A357",@"ios16_0_20A357_arm64e_carkit",@"0x1a6a70534",@NO,@NO];
    for(NSArray *p in profiles)if([Mode hasSuffix:p[0]]){selected=p;Mode=[Mode substringToIndex:Mode.length-[p[0] length]];break;}
    NSString *uuid=selected[1],*build=selected[2],*profileName=selected[3];ExpectedInvoke=selected[4];
    MutualField=[selected[5] boolValue];ExpandedSchema=[selected[6] boolValue];FixtureUUID=uuid;
    Class host=objc_getClass("CDHost16"),client=objc_getClass(ExpandedSchema?"CDClient17":"CDClient"),status=objc_getClass("CDStatus");
    BOOL legacyDispatch=[Mode hasPrefix:@"dispatch-"]&&[Mode hasSuffix:@"-legacy"];
    if(legacyDispatch){
        Mode=[Mode substringToIndex:Mode.length-7];
        FixtureUUID=uuid=@"E7918412-DF06-3E57-9E4E-C031AD370605";build=@"20G75";
        host=objc_getClass("CDLegacyHost");
    }
    if([Mode hasPrefix:@"dispatch-"]){
        NSDictionary *profile=CDV3FixtureHostProfile(host,client,status,Context(uuid,build,legacyDispatch));
        if([Mode isEqual:@"dispatch-unknown"]){NSMutableDictionary *changed=[profile mutableCopy];changed[@"selected_profile"]=@"unsupported";profile=changed;}
        if([Mode isEqual:@"dispatch-stale-image"])FixtureUUID=@"UNKNOWN";
        if([Mode isEqual:@"dispatch-wrong-method"]){
            Class bad=objc_allocateClassPair(objc_getClass("CDDispatchClient"),"BadDispatch",0);
            class_addMethod(bad,NSSelectorFromString(ExpandedSchema?@"startSessionWithHost:requestIdentifier:completion:":@"startSessionWithHost:completion:"),(IMP)WrongMethod,ExpandedSchema?"v40@0:8@16@24@32":"v32@0:8@16@24");
            objc_registerClassPair(bad);client=bad;
        }else client=objc_getClass("CDDispatchClient");
        __block unsigned callbacks=0;NSError *error=nil;
        BOOL result=CDV3RequestHostSessionFixture([[client alloc] init],@"host",profile,^(BOOL success,NSError *nativeError){
            callbacks++;Require(success==!ExpandedSchema,"BOOL callback argument changed");
            Require([nativeError.domain isEqual:@"Fixture.Native"]&&nativeError.code==(ExpandedSchema?43:42),"NSError callback argument changed");
        },&error);
        BOOL valid=[Mode isEqual:@"dispatch-valid"];
        Require(result==valid,"Wrong dispatch result");Require((error==nil)==valid,"Wrong dispatch error");
        Require(callbacks==(valid?1u:0u),"Invalid dispatch called completion");
        Require(OldRequests==(valid&&!ExpandedSchema?1u:0u)&&NewRequests==(valid&&ExpandedSchema?1u:0u),"Wrong selector dispatched");
    }else if([Mode hasPrefix:@"profile-"]){
        NSDictionary *context=Context(uuid,build,NO);NSString *expected=@"unsupported";
        if([Mode isEqual:@"profile-new"]){expected=profileName;}
        else if([Mode isEqual:@"profile-legacy"]){host=objc_getClass("CDLegacyHost");context=Context(@"E7918412-DF06-3E57-9E4E-C031AD370605",@"20G75",YES);expected=@"legacy_ios16_6";}
        else if([Mode isEqual:@"profile-unknown"]){context=Context(@"UNKNOWN",@"20A357",NO);}
        else if([Mode isEqual:@"profile-different-build"]){NSMutableDictionary *changed=[Context(uuid,@"ANOTHER_BUILD",NO) mutableCopy];changed[@"os_version"]=@"ANOTHER_VERSION";context=changed;expected=profileName;}
        else if([Mode isEqual:@"profile-legacy-unverified"]){host=objc_getClass("CDLegacyHost");context=Context(@"E7918412-DF06-3E57-9E4E-C031AD370605",@"20G75",NO);}
        else if([Mode isEqual:@"profile-wrong-start-type"]){Class bad=objc_allocateClassPair(client,"WrongClient",0);class_addMethod(bad,NSSelectorFromString(ExpandedSchema?@"startSessionWithHost:requestIdentifier:completion:":@"startSessionWithHost:completion:"),(IMP)WrongMethod,ExpandedSchema?"v40@0:8@16@24@32":"v32@0:8@16@24");objc_registerClassPair(bad);client=bad;}
        else if([Mode isEqual:@"profile-mixed-method-uuid"]||[Mode isEqual:@"profile-unknown-method-uuid"]||[Mode isEqual:@"profile-foreign-method-owner"]){}
        else if([Mode isEqual:@"profile-foreign-class-image"]||[Mode isEqual:@"profile-foreign-implementation-image"]){
            NSMutableDictionary *changed=[context mutableCopy],*identity=[context[@"legacy_completion"] mutableCopy];
            identity[[Mode isEqual:@"profile-foreign-class-image"]?@"class_image":@"implementation_image"]=@"/tmp/foreign.dylib";
            changed[@"legacy_completion"]=identity;context=changed;
        }
        else Require(NO,"Unknown profile scenario");
        NSDictionary *profile=CDV3FixtureHostProfile(host,client,status,context);
        if(![profile[@"selected_profile"] isEqual:expected])fprintf(stderr,"%s\n",profile.description.UTF8String);
        Require([profile[@"selected_profile"] isEqual:expected],"Incorrect profile selection");
        Require(CDV3UsesDictionaryHostProfile(profile)==[expected isEqual:profileName],"Wrong dictionary construction branch");
        if([Mode isEqual:@"profile-new"]){
            NSDictionary *completion=profile[@"completion_identity"];
            Require([completion[@"typed_completion_enabled"] boolValue],"Direct completion evidence was not accepted");
            Require(![completion[@"daemon_identity_used_for_callback_abi"] boolValue]&&![completion[@"daemon_implementation_inspected"] boolValue],"Daemon evidence overstated");
            Require([completion[@"retained_block_signature"] isEqual:@"v20@?0B8@\"NSError\"12"],"Wrong block ABI");
            Require([completion[@"framework_uuid"] isEqual:uuid]&&[completion[@"reference_build"] isEqual:build],"Completion evidence belongs to another profile");
            Require([completion[@"reply_invoke_address"] isEqual:ExpectedInvoke],"Wrong inspected reply implementation");
        }
        if([Mode isEqual:@"profile-legacy"])Require([profile[@"completion_identity"] isEqual:context[@"legacy_completion"]],"Legacy evidence changed");
        Require(Initializations==0,"Inspector constructed host");
        if([expected isEqual:profileName]){
            Require([profile[@"request_family"] isEqual:ExpandedSchema?@"host_request_identifier_completion":@"host_completion"],"Wrong selected request family");
            Require([profile[@"device_validation_required"] boolValue],"Profile claims device validation");
        }
    }else{
        NSString *key=[@"ab" stringByPaddingToLength:64 withString:@"ab" startingAtIndex:0];NSError *error=nil;
        if([Mode isEqual:@"wrong-method-type"]){Class bad=objc_allocateClassPair(host,"WrongHost",0);class_addMethod(bad,@selector(port),(IMP)WrongMethod,"@16@0:8");objc_registerClassPair(bad);host=bad;}
        if([Mode isEqual:@"invalid-key-type"])key=(id)[key dataUsingEncoding:NSUTF8StringEncoding];
        if([Mode isEqual:@"invalid-key-hex"])key=[key uppercaseString];
        id value=[Mode isEqual:@"production-owner-reject"]?CDV3CreateDictionaryHost(host,62000,key,&error):CDV3CreateDictionaryHostFixture(host,62000,key,&error);
        if([Mode isEqual:@"valid"]){
            if(error)fprintf(stderr,"%s\n",error.description.UTF8String);
            Require(value!=nil&&error==nil,"Valid host rejected");Require(Initializations==1,"Wrong initialization count");
            Require(Encodings==1&&Decodings==1,"Host fields were not checked through an actual secure archive");
        }
        else{
            Require(value==nil&&error!=nil,"Invalid host accepted");
            if([Mode isEqual:@"wrong-method-type"]||[Mode hasPrefix:@"invalid-key"]||[Mode isEqual:@"production-owner-reject"]||
               [Mode containsString:@"method-uuid"]||[Mode isEqual:@"foreign-method-owner"])
                Require(Initializations==0&&Encodings==0&&Decodings==0,"Rejected identity or input reached constructor/archive");
        }
    }
    puts("OK");return 0;
}}
