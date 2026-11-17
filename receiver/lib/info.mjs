// SPDX-License-Identifier: GPL-3.0-only
// DiPlay 615b32ce AirPlayInfoPlist / AirPlayHid protocol declarations.
import {plistBytes} from './plist.mjs';
export const width=1280,height=720,uuid='b7e6c5a0-1111-4000-8000-000000000001';
const finger=[0x05,0x0d,0x09,0x22,0xa1,0x02,0x09,0x38,0x75,0x08,0x95,0x01,0x81,0x02,0x15,0x00,0x25,0x01,0x09,0x33,0x75,0x01,0x95,0x01,0x81,0x02,0x95,0x07,0x81,0x03,0x05,0x01,0x26,width&255,width>>8,0x09,0x30,0x75,0x10,0x95,0x01,0x81,0x02,0x26,height&255,height>>8,0x09,0x31,0x81,0x02,0xc0];
const descriptor=Buffer.from([0x05,0x0d,0x09,0x04,0xa1,0x01,...finger,...finger,0xc0]);
export function info(){return {sourceVersion:'509.0',features:Number(0x615653aee2n&~0x10004540a00n),
 statusFlags:4,model:'CarDash Research',manufacturer:'CarDash',deviceID:'02:43:44:4c:41:42',bluetoothIDs:['02:43:44:4c:41:42'],name:'CarDash Native Research',rightHandDrive:false,keepAliveLowPower:false,keepAliveSendStatsAsBody:false,
 modes:{resources:[1,2].map(resourceID=>({resourceID,transferType:1,transferPriority:100,takeConstraint:100,borrowConstraint:100,unborrowConstraint:100})),appStates:[{appStateID:2,state:false},{appStateID:1,speechMode:-1},{appStateID:3,state:false}]},
 extendedFeatures:['enhancedRequestCarUI'],
 displays:[{uuid,type:110,maxFPS:30,widthPixels:width,heightPixels:height,widthPhysical:260,heightPhysical:146,features:8,primaryInputDevice:1,uiAppearanceMode:0,uiAppearanceSetting:0,mapAppearanceMode:0,mapAppearanceSetting:0,viewAreas:[{widthPixels:width,heightPixels:height,originXPixels:0,originYPixels:0,safeArea:{widthPixels:width,heightPixels:height,originXPixels:0,originYPixels:0,drawUIOutsideSafeArea:true}}],initialViewArea:0}],
 hidDevices:[{hidProductID:1,hidVendorID:2,hidCountryCode:0,uuid:'2a2a2a2a',name:'CarDash Research Touchscreen',displayUUID:uuid,hidDescriptor:plistBytes(descriptor)}]};}
export const receiverInfo=()=>({...info(),features:Number(0x615653aee2n),audioFormats:[{type:100,audioType:'media',audioOutputFormats:0xc3fc},{type:100,audioType:'default',audioOutputFormats:0xc3fc},{type:101,audioType:'default',audioOutputFormats:0xc3fc}],audioLatencies:[{type:100,inputLatencyMicros:0,outputLatencyMicros:0},{type:101,inputLatencyMicros:0,outputLatencyMicros:0}]});
