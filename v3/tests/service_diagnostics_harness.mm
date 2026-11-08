#import <Foundation/Foundation.h>
#import "../app/ServiceDiagnostics.h"
#include <stdio.h>

int main(int argc, char **argv) { @autoreleasepool {
    if (argc != 2) return 2;
    NSData *input = [[NSFileHandle fileHandleWithStandardInput] readDataToEndOfFile];
    NSDictionary *value = [NSJSONSerialization JSONObjectWithData:input options:0 error:nil];
    if (![value isKindOfClass:NSDictionary.class]) return 3;
    NSString *report = CDV3DiagnosticReport(value[@"reply"], @(argv[1]), value[@"context"]);
    NSData *output = [report dataUsingEncoding:NSUTF8StringEncoding];
    return fwrite(output.bytes, 1, output.length, stdout) == output.length ? 0 : 4;
} }
