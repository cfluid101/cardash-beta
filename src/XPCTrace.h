#import <Foundation/Foundation.h>

// Disposable diagnostic worker only. Observes this exact client and connections
// returned by its validated serviceConnection getter; never sends a request.
// Retains tracked identities and leaves process-local hooks installed until exit.
BOOL CDXPCTraceRegisterClient(id client, NSString *profile);
void CDXPCTraceBeginCleanup(void);
NSDictionary *CDXPCTraceSummary(void);
// JSON-safe bounded error facts (under 8 KiB), including at most two causes.
NSDictionary *CDXPCTraceError(NSError *error);
