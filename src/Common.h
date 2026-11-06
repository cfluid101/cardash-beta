#import <Foundation/Foundation.h>
#include <sys/types.h>

#define CD_VERSION @"0.1.0"
#define CD_ROOT @"/var/mobile/Library/CarDashDiagnostics"
#define CD_APP @"/var/jb/Applications/CarDashDiagnostics.app/CarDashDiagnostics"
#define CD_HELPER @"/var/jb/usr/libexec/cardash-diagnostics"
#define CD_JOB @"com.cfluid.cardash.diagnostics"

NSString *CDRoot(void);
NSString *CDSystem(const char *name);
NSData *CDJSON(id object);
void CDEmit(NSString *event, NSDictionary *fields);
double CDClock(void);
BOOL CDWrite(int fd, NSData *data);
BOOL CDMethodMatches(Class cls, NSString *selector, const char *ret, NSArray<NSString *> *args, BOOL classMethod, BOOL checkOwner);
NSString *CDConclusion(BOOL issued, BOOL callback, BOOL transport, BOOL observedNewSession);
NSDictionary *CDCommand(NSString *command);
int CDWorker(NSString *profile);
int CDDaemon(BOOL hostMode);
int CDPrepare(void);
