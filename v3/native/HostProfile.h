#import <Foundation/Foundation.h>

// Metadata only. Does not allocate or message private session objects.
NSDictionary *CDV3InspectHostProfile(Class host,Class client,Class status,NSDictionary *legacyCompletion);
BOOL CDV3UsesDictionaryHostProfile(NSDictionary *profile);

// Requires one exact inspected dictionary-host image; all methods must match
// that image. Verifies fields before/after secure coding; never requests a session.
id CDV3CreateDictionaryHost(Class host,NSInteger port,NSString *key,NSError **error);

#if CD_HOST_TEST
// Fixture owners/identities are accepted only in the separately compiled tests.
NSDictionary *CDV3FixtureHostProfile(Class host,Class client,Class status,NSDictionary *context);
id CDV3CreateDictionaryHostFixture(Class host,NSInteger port,NSString *key,NSError **error);
#endif
