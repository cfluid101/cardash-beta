#import <Foundation/Foundation.h>

NSDictionary *CDV3HostCompletionIdentity(Class client);

// Metadata only. Does not allocate or message private session objects.
NSDictionary *CDV3InspectHostProfile(Class host,Class client,Class status,NSDictionary *legacyCompletion);
BOOL CDV3UsesDictionaryHostProfile(NSDictionary *profile);
BOOL CDV3RequestHostSession(id client,id host,NSDictionary *profile,void(^completion)(BOOL,NSError *),NSError **error);

// Requires one exact inspected dictionary-host image; all methods must match
// that image. Verifies fields before/after secure coding; never requests a session.
id CDV3CreateDictionaryHost(Class host,NSInteger port,NSString *key,NSError **error);

#if CD_HOST_TEST
BOOL CDV3RequestHostSessionFixture(id client,id host,NSDictionary *profile,void(^completion)(BOOL,NSError *),NSError **error);
// Fixture owners/identities are accepted only in the separately compiled tests.
NSDictionary *CDV3FixtureHostProfile(Class host,Class client,Class status,NSDictionary *context);
id CDV3CreateDictionaryHostFixture(Class host,NSInteger port,NSString *key,NSError **error);
#endif
