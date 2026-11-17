// SPDX-License-Identifier: GPL-3.0-only
#import <Foundation/Foundation.h>

// Produces a shareable report even when the receiver service cannot be reached.
// stateDirectory is supplied by the caller; no filesystem root discovery occurs.
NSString *CDV3DiagnosticReport(NSDictionary *serviceReply, NSString *stateDirectory,
                              NSDictionary *context);
