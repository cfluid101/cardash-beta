// SPDX-License-Identifier: GPL-3.0-only
#pragma once
#include <cstdint>
#include <cstddef>
#include <mach/mach.h>
#include <mach/vm_map.h>

using CDV3AudioRegionQuery=kern_return_t (*)(vm_map_read_t,vm_address_t *,
    vm_size_t *,natural_t *,vm_region_recurse_info_t,mach_msg_type_number_t *);

static inline bool CDV3AudioMapped(uintptr_t address,size_t bytes,vm_prot_t required,
                                  CDV3AudioRegionQuery query=vm_region_recurse_64) {
    if (!bytes || !query) return false;
    natural_t depth=0;
    for (unsigned attempt=0;attempt<64;attempt++) {
        // A containing shared-cache submap can be R while its leaf is RX.
        // The query overwrites region with the container start. Always restore
        // the target address before descending, rather than inspect its first leaf.
        vm_address_t region=address;
        vm_size_t size=0;
        vm_region_submap_info_data_64_t info={};
        mach_msg_type_number_t count=VM_REGION_SUBMAP_INFO_COUNT_64;
        kern_return_t result=query(mach_task_self(),&region,&size,&depth,
            (vm_region_recurse_info_t)&info,&count);
        if (result!=KERN_SUCCESS || count<VM_REGION_SUBMAP_INFO_V0_COUNT_64 ||
            region>address || address-region>size || bytes>size-(address-region)) return false;
        if (!info.is_submap) return (info.protection&required)==required;
        if (depth>=63) return false;
        depth++;
    }
    return false;
}
