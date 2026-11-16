// SPDX-License-Identifier: GPL-3.0-only
// Locate the Substrate-compatible inline hook entry point.
#pragma once
#include <dlfcn.h>

using CDV3HookFunctionType=void (*)(void *,void *,void **);

// Beta 5 opened only the first path and reported "hook provider unavailable"
// on bootstraps that ship the same API elsewhere. The original path stays
// first so a phone that worked before resolves exactly the provider it used.
// Every candidate exports the same MSHookFunction ABI; none relaxes a
// framework identity, instruction or layout check.
static const char *const CDV3HookProviderPaths[]={
    "/var/jb/usr/lib/libsubstrate.dylib",
    "/var/jb/usr/lib/libellekit.dylib",
    "/var/jb/Library/Frameworks/CydiaSubstrate.framework/CydiaSubstrate",
    "/var/jb/usr/lib/libsubstitute.dylib",
};

template<typename Open,typename Lookup>
static inline CDV3HookFunctionType CDV3ResolveHookFunctionWith(Open open,Lookup lookup,const char **source=nullptr) {
    if(source)*source=nullptr;
    for(const char *path:CDV3HookProviderPaths) {
        void *handle=open(path);
        if(!handle)continue;
        if(void *symbol=lookup(handle,"MSHookFunction")) {
            if(source)*source=path;
            return (CDV3HookFunctionType)symbol;
        }
    }
    // The injector that loaded this adapter may already expose the API from
    // an image at a path this list does not know.
    if(void *symbol=lookup(RTLD_DEFAULT,"MSHookFunction")) {
        if(source)*source="already-loaded image";
        return (CDV3HookFunctionType)symbol;
    }
    return nullptr;
}

static inline CDV3HookFunctionType CDV3ResolveHookFunction(const char **source=nullptr) {
    return CDV3ResolveHookFunctionWith(
        [](const char *path){return dlopen(path,RTLD_NOW|RTLD_LOCAL);},
        [](void *handle,const char *name){return dlsym(handle,name);},source);
}
