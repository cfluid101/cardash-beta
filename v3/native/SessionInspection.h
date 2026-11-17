#import <Foundation/Foundation.h>

// Metadata only: does not allocate private session objects or invoke their
// methods. The caller supplies the time bound; the CLI uses an eight-second
// alarm. An explicit path permits real fixture-image tests without CarKit.
NSDictionary *CDV3InspectCarKitAtPath(NSString *frameworkPath);
