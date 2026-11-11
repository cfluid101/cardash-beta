// SPDX-License-Identifier: GPL-3.0-only
#import "ServiceDiagnostics.h"
#include <errno.h>
#include <fcntl.h>
#include <math.h>
#include <sys/stat.h>
#include <unistd.h>

namespace {
constexpr NSUInteger LogLimit = 64 * 1024;
constexpr NSUInteger ServiceReportLimit = 2 * 1024 * 1024;
constexpr NSUInteger RecordLimit = 256 * 1024;
constexpr NSUInteger ExportLimit = 4 * 1024 * 1024;

static id Scalar(id value) {
    if ([value isKindOfClass:NSString.class]) {
        NSString *text = value;
        return text.length > 1024 ? [text substringToIndex:1024] : text;
    }
    if ([value isKindOfClass:NSNumber.class] && isfinite([value doubleValue])) return value;
    return value == NSNull.null ? value : nil;
}

static NSMutableDictionary *Fields(id value, NSArray<NSString *> *names) {
    NSMutableDictionary *result = [NSMutableDictionary dictionary];
    if (![value isKindOfClass:NSDictionary.class]) return result;
    for (NSString *name in names) {
        id field = Scalar(value[name]);
        if (field) result[name] = field;
    }
    return result;
}

static NSDictionary *Context(id value) {
    NSMutableDictionary *result = Fields(value, @[@"packageVersion", @"appVersion", @"machine",
        @"osVersion", @"build", @"uid", @"euid", @"gid", @"appPath", @"executablePath",
        @"socketPath", @"stateDirectory", @"rootPath", @"rootSource", @"rootError"]);
    if ([value isKindOfClass:NSDictionary.class] && [value[@"pathChecks"] isKindOfClass:NSArray.class]) {
        NSMutableArray *checks = [NSMutableArray array];
        for (id item in value[@"pathChecks"]) {
            if (checks.count == 16) break;
            if (![item isKindOfClass:NSDictionary.class]) continue;
            [checks addObject:Fields(item, @[@"path", @"exists", @"errno", @"type", @"uid", @"gid",
                                             @"mode", @"readable", @"executable"])];
        }
        result[@"pathChecks"] = checks;
    }
    return result;
}

static NSDictionary *Status(id value) {
    NSMutableDictionary *result = Fields(value, @[@"version", @"active", @"identityReady", @"preparing",
        @"nativeFrames", @"codec", @"videoConnected", @"eventConnected", @"error", @"sessionSeconds",
        @"sessionLimitSeconds", @"audioSupported", @"audioOutput", @"microphoneSupported",
        @"sourceWidth", @"sourceHeight", @"displayVerified"]);
    if (![value isKindOfClass:NSDictionary.class]) return result;
    NSDictionary *nested = @{
        @"transport": @[@"ready", @"pid", @"imageUUID", @"error", @"code"],
        @"network": @[@"ready", @"url", @"error"],
        @"videoBudget": @[@"ready", @"pid", @"code", @"error", @"targetBps", @"measuredBps", @"requestedBps", @"nativeBps", @"appliedBps"],
        @"audioRouting": @[@"ready", @"pid", @"code", @"error", @"deviceOutputActive", @"leaseValid", @"ownHost"],
        @"native": @[@"present", @"authenticated", @"activated", @"timing_requests", @"timing_replies"]
    };
    for (NSString *name in nested) {
        if ([value[name] isKindOfClass:NSDictionary.class]) result[name] = Fields(value[name], nested[name]);
    }
    return result;
}

static bool Append(NSMutableData *output, NSDictionary *record) {
    NSData *json = [NSJSONSerialization dataWithJSONObject:record options:NSJSONWritingSortedKeys error:nil];
    if (!json || json.length + 1 > ExportLimit - output.length) return false;
    [output appendData:json]; [output appendBytes:"\n" length:1]; return true;
}

static NSDictionary *LogError(NSString *name, NSString *reason, int error) {
    return @{@"event": @"supporting_log_error", @"file": name, @"reason": reason, @"errno": @(error)};
}

static NSDictionary *ReadLog(int directory, int directoryError, NSString *name) {
    if (directory < 0) return LogError(name, @"state_directory_unavailable", directoryError);
    int fd = openat(directory, name.fileSystemRepresentation, O_RDONLY | O_CLOEXEC | O_NOFOLLOW | O_NONBLOCK);
    if (fd < 0) return LogError(name, @"open_failed", errno);
    struct stat info = {};
    if (fstat(fd, &info) < 0) {
        int error = errno; close(fd); return LogError(name, @"stat_failed", error);
    }
    if (!S_ISREG(info.st_mode) || info.st_size < 0) {
        close(fd); return LogError(name, @"not_regular", EINVAL);
    }
    off_t offset = info.st_size > (off_t)LogLimit ? info.st_size - (off_t)LogLimit : 0;
    NSUInteger count = (NSUInteger)(info.st_size - offset);
    NSMutableData *data = [NSMutableData dataWithLength:count];
    NSUInteger used = 0;
    while (used < count) {
        ssize_t n = pread(fd, (char *)data.mutableBytes + used, count - used, offset + (off_t)used);
        if (n < 0 && errno == EINTR) continue;
        if (n < 0) { int error = errno; close(fd); return LogError(name, @"read_failed", error); }
        if (n == 0) break;
        used += (NSUInteger)n;
    }
    close(fd); data.length = used;
    NSString *text = [[NSString alloc] initWithData:data encoding:NSUTF8StringEncoding];
    BOOL fallback = text == nil;
    if (fallback) text = [[NSString alloc] initWithData:data encoding:NSISOLatin1StringEncoding];
    return @{@"event": @"supporting_log", @"file": name, @"text": text ?: @"",
             @"bytesRead": @(used), @"sizeBytes": @(info.st_size), @"truncated": @(offset > 0),
             @"encoding": fallback ? @"latin1_fallback" : @"utf8"};
}

static void AppendServiceReport(NSMutableData *output, NSString *report) {
    NSData *data = [report dataUsingEncoding:NSUTF8StringEncoding];
    const uint8_t *bytes = (const uint8_t *)data.bytes;
    NSUInteger start = data.length > ServiceReportLimit ? data.length - ServiceReportLimit : 0;
    BOOL truncated = start > 0;
    if (start && bytes[start - 1] != '\n') {
        while (start < data.length && bytes[start] != '\n') ++start;
        if (start < data.length) ++start;
    }
    NSUInteger invalid = 0, oversized = 0;
    for (NSUInteger at = start; at < data.length;) {
        NSUInteger end = at;
        while (end < data.length && bytes[end] != '\n') ++end;
        NSUInteger length = end - at;
        if (length > RecordLimit) ++oversized;
        else if (length) {
            NSData *line = [NSData dataWithBytes:bytes + at length:length];
            id record = [NSJSONSerialization JSONObjectWithData:line options:0 error:nil];
            if ([record isKindOfClass:NSDictionary.class]) {
                if (!Append(output, record)) { truncated = YES; break; }
            } else ++invalid;
        }
        at = end + 1;
    }
    if (truncated || invalid || oversized) Append(output, @{@"event": @"report_read_warning",
        @"truncated": @(truncated), @"invalidRecords": @(invalid), @"oversizedRecords": @(oversized)});
}
}

NSString *CDV3DiagnosticReport(NSDictionary *serviceReply, NSString *stateDirectory,
                              NSDictionary *context) {
    NSDictionary *reply = [serviceReply isKindOfClass:NSDictionary.class] ? serviceReply : @{};
    NSString *report = [reply[@"report"] isKindOfClass:NSString.class] ? reply[@"report"] : nil;
    BOOL live = report.length > 0;
    NSMutableData *output = [NSMutableData data];
    Append(output, @{@"event": @"app_export", @"schemaVersion": @1,
        @"report_scope": live ? @"service_report" : @"offline_service_diagnostics",
        @"serviceError": Fields(reply, @[@"error", @"errno", @"errnoName", @"stage", @"socketPath"]),
        @"context": Context(context), @"status": Status(reply[@"status"])});
    if (live) AppendServiceReport(output, report);
    else {
        int directory = -1, error = EINVAL;
        if ([stateDirectory isKindOfClass:NSString.class] && stateDirectory.length) {
            directory = open(stateDirectory.fileSystemRepresentation, O_RDONLY | O_CLOEXEC | O_DIRECTORY | O_NOFOLLOW);
            error = directory < 0 ? errno : 0;
        }
        for (NSString *name in @[@"installation.log", @"service-bootstrap.log"])
            Append(output, ReadLog(directory, error, name));
        if (directory >= 0) close(directory);
    }
    return [[NSString alloc] initWithData:output encoding:NSUTF8StringEncoding] ?: @"";
}
