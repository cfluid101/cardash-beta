#import <Foundation/Foundation.h>

// Bounded, read-only identity checks. Unknown identities never enable typed
// interpretation of the private completion block.
NSString *CDMachOUUID(NSData *data);
NSDictionary *CDNativeFileIdentity(NSString *path);
NSString *CDLoadedImageUUID(const void *header);
BOOL CDCarKitCompletionIdentityMatches(NSDictionary *facts);
NSDictionary *CDCarKitCompletionIdentity(Class clientClass);
