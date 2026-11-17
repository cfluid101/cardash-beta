#import "HostPayload.h"
#import <objc/message.h>

NSString *CDPublicKeyString(NSData *key) {
    if(![key isKindOfClass:NSData.class]||key.length!=32)return nil;
    const unsigned char *bytes=(const unsigned char *)key.bytes;NSMutableString *value=[NSMutableString stringWithCapacity:64];
    for(NSUInteger i=0;i<key.length;i++)[value appendFormat:@"%02x",bytes[i]];return value;
}
id CDSecureHostRoundTrip(id host,NSError **error) {
    if(error)*error=nil;
    @try {
        // macOS archive decoding can tolerate a class mismatch that iOS XPC
        // rejects. Enforce the observed iOS16 NSString contract explicitly.
        SEL selector=NSSelectorFromString(@"publicKey");
        id key=[host respondsToSelector:selector]?((id(*)(id,SEL))objc_msgSend)(host,selector):nil;
        if(!host||![host respondsToSelector:selector]||(key&&![key isKindOfClass:NSString.class])){
            if(error)*error=[NSError errorWithDomain:@"CarDashDiagnostic.HostSerialization" code:2 userInfo:@{NSLocalizedDescriptionKey:@"publicKey must be NSString or nil for the observed iOS16 CarKit decoder"}];return nil;
        }
        NSData *archive=[NSKeyedArchiver archivedDataWithRootObject:host requiringSecureCoding:YES error:error];
        if(!archive)return nil;
        return [NSKeyedUnarchiver unarchivedObjectOfClass:[host class] fromData:archive error:error];
    } @catch(NSException *exception) {
        if(error)*error=[NSError errorWithDomain:@"CarDashDiagnostic.HostSerialization" code:1 userInfo:@{NSLocalizedDescriptionKey:exception.reason?:exception.name}];return nil;
    }
}
