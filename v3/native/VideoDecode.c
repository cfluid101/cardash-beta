// SPDX-License-Identifier: GPL-3.0-only
// Native AVC access units -> bounded latest JPEG. No screen capture, networking,
// file access or audio/session changes. Public VideoToolbox and ImageIO APIs.
#include <VideoToolbox/VideoToolbox.h>
#include <CoreMedia/CoreMedia.h>
#include <CoreVideo/CoreVideo.h>
#include <CoreGraphics/CoreGraphics.h>
#include <ImageIO/ImageIO.h>
#include <pthread.h>
#include <stdint.h>
#include <stdbool.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <time.h>

enum { CDV_MAX_BYTES=4*1024*1024, CDV_MAX_PIXELS=921600, CDV_MAX_PENDING=8 };
enum { CDV_BAD_ARGUMENT=-71001, CDV_NO_MEMORY=-71002, CDV_BAD_CONFIG=-71003,
       CDV_BAD_DIMENSIONS=-71004, CDV_BAD_FRAME=-71005, CDV_JPEG_FAILED=-71006 };
enum { CDV_STAGE_NONE=0, CDV_STAGE_VALIDATE=1, CDV_STAGE_BLOCK_CREATE=2,
       CDV_STAGE_BLOCK_COPY=3, CDV_STAGE_SAMPLE_CREATE=4, CDV_STAGE_SUBMIT=5,
       CDV_STAGE_CALLBACK=6, CDV_STAGE_JPEG=7 };
typedef struct {
 uint64_t submitted,decoded,jpegFrames,inputDrops,decodedDrops,outputReplaced;
 uint64_t decodeFailures,jpegFailures,pending,maxPending,latestSequence,latestBytes;
 uint64_t workerBusy,waitingForKeyframe;
 int64_t hardwareAcceleration,lastStatus;
 uint64_t lastFailureStage,lastInputBytes,lastInputTimestamp,lastInputKeyframe;
 uint64_t lastDecodeFlags,lastCallbackFlags,hardwareSupported;
 int64_t lastSubmitStatus,lastCallbackStatus,realTimeStatus;
} CDVStats;
typedef struct { uint64_t sequence,timestamp; uint32_t size,width,height; } CDVFrame;
typedef struct { uint64_t sequence,timestamp; bool used; } CDVSlot;
typedef struct {
 pthread_mutex_t mutex; pthread_cond_t condition; pthread_t worker; bool workerStarted,closing;
 VTDecompressionSessionRef session; CMVideoFormatDescriptionRef format;
 uint32_t width,height,fps; CGRect crop; CDVSlot slots[CDV_MAX_PENDING]; uint64_t nextSequence;
 CVPixelBufferRef pixel; uint64_t pixelTimestamp; uint64_t highestTimestamp; bool haveTimestamp;
 uint8_t *jpeg; CDVFrame latest; CDVStats stats;
} CDVideo;
typedef struct { uint8_t *bytes; size_t length,capacity; bool failed; } CDVOutput;

static double monotonic_seconds(void) { struct timespec t; clock_gettime(CLOCK_MONOTONIC,&t);return (double)t.tv_sec+(double)t.tv_nsec/1e9; }
static struct timespec wait_deadline(double seconds) {
 struct timespec t;clock_gettime(CLOCK_REALTIME,&t);int64_t n=(int64_t)t.tv_nsec+(int64_t)(seconds*1e9);
 t.tv_sec+=(time_t)(n/1000000000);t.tv_nsec=(long)(n%1000000000);return t;
}
static uint32_t be32(const uint8_t *p) {return ((uint32_t)p[0]<<24)|((uint32_t)p[1]<<16)|((uint32_t)p[2]<<8)|p[3];}
static bool access_unit(const uint8_t *bytes,uint32_t size,bool *key) {
 if(!bytes||size<5||size>CDV_MAX_BYTES)return false;uint32_t at=0,nals=0;*key=false;
 while(at<size){
  if(size-at<4||++nals>8192)return false;uint32_t n=be32(bytes+at);at+=4;
  if(!n||n>size-at)return false;unsigned type=bytes[at]&31;
  if(type<1||type>23)return false;if(type==5)*key=true;at+=n;
 }
 return true;
}
static size_t output_bytes(void *opaque,const void *data,size_t count) {
 CDVOutput *out=opaque;
 if(out->failed||count>CDV_MAX_BYTES-out->length){out->failed=true;return 0;}
 size_t required=out->length+count;
 if(required>out->capacity){size_t capacity=out->capacity?out->capacity:65536;while(capacity<required)capacity*=2;
  if(capacity>CDV_MAX_BYTES)capacity=CDV_MAX_BYTES;uint8_t *next=realloc(out->bytes,capacity);
  if(!next){out->failed=true;return 0;}out->bytes=next;out->capacity=capacity;
 }
 memcpy(out->bytes+out->length,data,count);out->length+=count;return count;
}
static uint8_t *make_jpeg(CDVideo *owner,CVPixelBufferRef pixel,uint32_t *size) {
 *size=0;uint8_t *result=NULL;CGColorSpaceRef colors=NULL;CGContextRef bitmap=NULL;CGImageRef image=NULL,cropped=NULL;
 CGDataConsumerRef consumer=NULL;CGImageDestinationRef destination=NULL;CFNumberRef quality=NULL;CFDictionaryRef options=NULL;
 CDVOutput out={0};
 if(CVPixelBufferGetPixelFormatType(pixel)!=kCVPixelFormatType_32BGRA||CVPixelBufferLockBaseAddress(pixel,kCVPixelBufferLock_ReadOnly)!=kCVReturnSuccess)return NULL;
 size_t w=CVPixelBufferGetWidth(pixel),h=CVPixelBufferGetHeight(pixel),stride=CVPixelBufferGetBytesPerRow(pixel);void *base=CVPixelBufferGetBaseAddress(pixel);
 if(!base||w>4096||h>4096||stride<w*4)goto done;
 colors=CGColorSpaceCreateWithName(kCGColorSpaceSRGB);if(!colors)goto done;
 bitmap=CGBitmapContextCreate(base,w,h,8,stride,colors,kCGBitmapByteOrder32Little|kCGImageAlphaPremultipliedFirst);if(!bitmap)goto done;
 image=CGBitmapContextCreateImage(bitmap);if(!image)goto done;
 CGRect crop=(w==owner->width&&h==owner->height)?CGRectMake(0,0,w,h):owner->crop;
 if(crop.origin.x<0||crop.origin.y<0||CGRectGetMaxX(crop)>w||CGRectGetMaxY(crop)>h||crop.size.width!=owner->width||crop.size.height!=owner->height)goto done;
 cropped=CGImageCreateWithImageInRect(image,crop);if(!cropped||CGImageGetWidth(cropped)!=owner->width||CGImageGetHeight(cropped)!=owner->height)goto done;
 CGDataConsumerCallbacks callbacks={output_bytes,NULL};consumer=CGDataConsumerCreate(&out,&callbacks);if(!consumer)goto done;
 destination=CGImageDestinationCreateWithDataConsumer(consumer,CFSTR("public.jpeg"),1,NULL);if(!destination)goto done;
 double q=.76;quality=CFNumberCreate(kCFAllocatorDefault,kCFNumberDoubleType,&q);if(!quality)goto done;
 const void *keys[]={kCGImageDestinationLossyCompressionQuality},*values[]={quality};
 options=CFDictionaryCreate(kCFAllocatorDefault,keys,values,1,&kCFTypeDictionaryKeyCallBacks,&kCFTypeDictionaryValueCallBacks);if(!options)goto done;
 CGImageDestinationAddImage(destination,cropped,options);
 if(CGImageDestinationFinalize(destination)&&!out.failed&&out.length>0&&out.length<=CDV_MAX_BYTES){result=out.bytes;*size=(uint32_t)out.length;out.bytes=NULL;}
 done:
 if(options)CFRelease(options);if(quality)CFRelease(quality);if(destination)CFRelease(destination);if(consumer)CGDataConsumerRelease(consumer);
 if(cropped)CGImageRelease(cropped);if(image)CGImageRelease(image);if(bitmap)CGContextRelease(bitmap);if(colors)CGColorSpaceRelease(colors);
 CVPixelBufferUnlockBaseAddress(pixel,kCVPixelBufferLock_ReadOnly);free(out.bytes);return result;
}
static void *jpeg_worker(void *opaque) {
 CDVideo *owner=opaque;double next=0;
 pthread_mutex_lock(&owner->mutex);
 while(!owner->closing){
  if(!owner->pixel){pthread_cond_wait(&owner->condition,&owner->mutex);continue;}
  double delay=next-monotonic_seconds();if(delay>0){struct timespec deadline=wait_deadline(delay);pthread_cond_timedwait(&owner->condition,&owner->mutex,&deadline);continue;}
  CVPixelBufferRef pixel=owner->pixel;uint64_t timestamp=owner->pixelTimestamp;owner->pixel=NULL;owner->stats.workerBusy=1;
  next=monotonic_seconds()+1.0/owner->fps;pthread_mutex_unlock(&owner->mutex);
  uint32_t size=0;uint8_t *jpeg=make_jpeg(owner,pixel,&size);CVPixelBufferRelease(pixel);
  pthread_mutex_lock(&owner->mutex);owner->stats.workerBusy=0;
  if(owner->closing){free(jpeg);break;}
  if(jpeg){uint8_t *old=owner->jpeg;owner->jpeg=jpeg;owner->latest=(CDVFrame){owner->latest.sequence+1,timestamp,size,owner->width,owner->height};
   owner->stats.jpegFrames++;owner->stats.latestSequence=owner->latest.sequence;owner->stats.latestBytes=size;if(old)owner->stats.outputReplaced++;free(old);
  }else{owner->stats.jpegFailures++;owner->stats.lastStatus=CDV_JPEG_FAILED;owner->stats.lastFailureStage=CDV_STAGE_JPEG;}
 }
 pthread_mutex_unlock(&owner->mutex);return NULL;
}
static int slot_for(CDVideo *owner,uint64_t sequence) {for(int i=0;i<CDV_MAX_PENDING;i++)if(owner->slots[i].used&&owner->slots[i].sequence==sequence)return i;return -1;}
static void complete_error(CDVideo *owner,uint64_t sequence,OSStatus status,uint64_t stage) {
 pthread_mutex_lock(&owner->mutex);int index=slot_for(owner,sequence);
 if(index>=0){owner->slots[index].used=false;owner->stats.pending--;owner->stats.decodeFailures++;owner->stats.lastStatus=status;owner->stats.lastFailureStage=stage;owner->stats.waitingForKeyframe=1;}
 pthread_mutex_unlock(&owner->mutex);
}
static void decoded(void *opaque,void *reference,OSStatus status,VTDecodeInfoFlags flags,CVImageBufferRef image,CMTime pts,CMTime duration) {
 (void)pts;(void)duration;CDVideo *owner=opaque;CVPixelBufferRef old=NULL;
 pthread_mutex_lock(&owner->mutex);int index=slot_for(owner,(uint64_t)(uintptr_t)reference);
 if(index<0){pthread_mutex_unlock(&owner->mutex);return;}
 uint64_t timestamp=owner->slots[index].timestamp;owner->slots[index].used=false;owner->stats.pending--;
 owner->stats.lastCallbackStatus=status;owner->stats.lastCallbackFlags=flags;
 if(!owner->closing){
  if(status||!image||(flags&kVTDecodeInfo_FrameDropped)){owner->stats.decodeFailures++;owner->stats.lastStatus=status?status:CDV_BAD_FRAME;owner->stats.lastFailureStage=CDV_STAGE_CALLBACK;owner->stats.waitingForKeyframe=1;}
  else{
   owner->stats.decoded++;
   if(owner->haveTimestamp&&timestamp<=owner->highestTimestamp)owner->stats.decodedDrops++;
   else{
    owner->haveTimestamp=true;owner->highestTimestamp=timestamp;CVPixelBufferRetain(image);old=owner->pixel;
    if(old)owner->stats.decodedDrops++;owner->pixel=image;owner->pixelTimestamp=timestamp;pthread_cond_signal(&owner->condition);
   }
  }
 }
 pthread_mutex_unlock(&owner->mutex);if(old)CVPixelBufferRelease(old);
}
void cd_video_destroy(void *handle,CDVStats *final_stats) {
 CDVideo *owner=handle;if(!owner)return;
 pthread_mutex_lock(&owner->mutex);owner->closing=true;pthread_cond_broadcast(&owner->condition);pthread_mutex_unlock(&owner->mutex);
 if(owner->session){VTDecompressionSessionFinishDelayedFrames(owner->session);VTDecompressionSessionWaitForAsynchronousFrames(owner->session);VTDecompressionSessionInvalidate(owner->session);CFRelease(owner->session);}
 if(owner->workerStarted)pthread_join(owner->worker,NULL);
 if(owner->pixel)CVPixelBufferRelease(owner->pixel);if(owner->format)CFRelease(owner->format);free(owner->jpeg);
 if(final_stats){owner->stats.pending=0;owner->stats.workerBusy=0;owner->stats.latestBytes=0;*final_stats=owner->stats;}
 pthread_cond_destroy(&owner->condition);pthread_mutex_destroy(&owner->mutex);free(owner);
}
void *cd_video_create(const uint8_t *config,uint32_t config_size,uint32_t width,uint32_t height,uint32_t fps,int32_t *error) {
 if(error)*error=CDV_BAD_ARGUMENT;
 if(!config||config_size<9||config_size>65536||config[0]!=1||(config[4]&3)!=3||width<2||height<2||width>4096||height>4096||(uint64_t)width*height>CDV_MAX_PIXELS||fps<1||fps>10)return NULL;
 const uint8_t *sets[64];size_t lengths[64];size_t count=0,at=6;
 for(int type=7;type<=8;type++){
  if(at>=config_size)return NULL;unsigned n=type==7?(config[5]&31):config[at++];if(!n||n>31)return NULL;
  for(unsigned i=0;i<n;i++){
   if(config_size-at<2||count>=64)return NULL;size_t length=((size_t)config[at]<<8)|config[at+1];at+=2;
   if(!length||length>config_size-at||(config[at]&31)!=type)return NULL;sets[count]=config+at;lengths[count++]=length;at+=length;
  }
 }
 CDVideo *owner=calloc(1,sizeof(*owner));if(!owner){if(error)*error=CDV_NO_MEMORY;return NULL;}
 if(pthread_mutex_init(&owner->mutex,NULL)){free(owner);if(error)*error=CDV_NO_MEMORY;return NULL;}
 if(pthread_cond_init(&owner->condition,NULL)){pthread_mutex_destroy(&owner->mutex);free(owner);if(error)*error=CDV_NO_MEMORY;return NULL;}
 owner->width=width;owner->height=height;owner->fps=fps;owner->stats.waitingForKeyframe=1;owner->stats.hardwareAcceleration=-1;
 OSStatus status=CMVideoFormatDescriptionCreateFromH264ParameterSets(kCFAllocatorDefault,count,sets,lengths,4,&owner->format);
 if(!status){CGSize dimensions=CMVideoFormatDescriptionGetPresentationDimensions(owner->format,false,true);CMVideoDimensions coded=CMVideoFormatDescriptionGetDimensions(owner->format);owner->crop=CMVideoFormatDescriptionGetCleanAperture(owner->format,true);
  if(!isfinite(dimensions.width)||!isfinite(dimensions.height)||fabs(dimensions.width-width)>.01||fabs(dimensions.height-height)>.01)status=CDV_BAD_DIMENSIONS;
  if(coded.width<2||coded.height<2||coded.width>4096||coded.height>4096||(uint64_t)coded.width*coded.height>CDV_MAX_PIXELS+131072)status=CDV_BAD_DIMENSIONS;
 }
 if(!status){
  int32_t pixelFormat=kCVPixelFormatType_32BGRA;CFNumberRef pixel=CFNumberCreate(kCFAllocatorDefault,kCFNumberSInt32Type,&pixelFormat);
  CFDictionaryRef surface=CFDictionaryCreate(kCFAllocatorDefault,NULL,NULL,0,&kCFTypeDictionaryKeyCallBacks,&kCFTypeDictionaryValueCallBacks);
  const void *keys[]={kCVPixelBufferPixelFormatTypeKey,kCVPixelBufferIOSurfacePropertiesKey},*values[]={pixel,surface};
  CFDictionaryRef attributes=pixel&&surface?CFDictionaryCreate(kCFAllocatorDefault,keys,values,2,&kCFTypeDictionaryKeyCallBacks,&kCFTypeDictionaryValueCallBacks):NULL;
  // iOS 16 chooses its platform decoder without this newer public hint.
  // Do not weak-link an iOS 17-only property into the 16.6 startup path.
  CFDictionaryRef specification=NULL;
  if(__builtin_available(macOS 10.9,iOS 17.0,tvOS 17.0,*)){
   const void *decoderKeys[]={kVTVideoDecoderSpecification_EnableHardwareAcceleratedVideoDecoder},*decoderValues[]={kCFBooleanTrue};
   specification=CFDictionaryCreate(kCFAllocatorDefault,decoderKeys,decoderValues,1,&kCFTypeDictionaryKeyCallBacks,&kCFTypeDictionaryValueCallBacks);
   if(!specification)status=CDV_NO_MEMORY;
  }
  VTDecompressionOutputCallbackRecord callback={decoded,owner};
  if(!pixel||!surface||!attributes)status=CDV_NO_MEMORY;
  if(!status)status=VTDecompressionSessionCreate(kCFAllocatorDefault,owner->format,specification,attributes,&callback,&owner->session);
  if(specification)CFRelease(specification);if(attributes)CFRelease(attributes);if(surface)CFRelease(surface);if(pixel)CFRelease(pixel);
 }
 if(!status){
  owner->stats.hardwareSupported=VTIsHardwareDecodeSupported(kCMVideoCodecType_H264);
  owner->stats.realTimeStatus=VTSessionSetProperty(owner->session,kVTDecompressionPropertyKey_RealTime,kCFBooleanTrue);
  if(__builtin_available(macOS 10.9,iOS 17.0,tvOS 17.0,*)){
   CFTypeRef hardware=NULL;if(!VTSessionCopyProperty(owner->session,kVTDecompressionPropertyKey_UsingHardwareAcceleratedVideoDecoder,kCFAllocatorDefault,&hardware)&&hardware){if(CFGetTypeID(hardware)==CFBooleanGetTypeID())owner->stats.hardwareAcceleration=CFBooleanGetValue((CFBooleanRef)hardware);CFRelease(hardware);}
  }
  if(pthread_create(&owner->worker,NULL,jpeg_worker,owner))status=CDV_NO_MEMORY;else owner->workerStarted=true;
 }
 if(status){if(error)*error=status;cd_video_destroy(owner,NULL);return NULL;}
 if(error)*error=0;return owner;
}
int32_t cd_video_feed(void *handle,const uint8_t *bytes,uint32_t size,uint64_t timestamp) {
 CDVideo *owner=handle;if(!owner)return -1;bool key=false;
 if(timestamp>INT64_MAX||!access_unit(bytes,size,&key)){pthread_mutex_lock(&owner->mutex);owner->stats.decodeFailures++;owner->stats.lastStatus=CDV_BAD_ARGUMENT;owner->stats.lastFailureStage=CDV_STAGE_VALIDATE;pthread_mutex_unlock(&owner->mutex);return -1;}
 pthread_mutex_lock(&owner->mutex);
 if(owner->closing){pthread_mutex_unlock(&owner->mutex);return -1;}
 if(owner->stats.pending>=CDV_MAX_PENDING){owner->stats.inputDrops++;owner->stats.waitingForKeyframe=1;pthread_mutex_unlock(&owner->mutex);return 0;}
 if(owner->stats.waitingForKeyframe&&!key){owner->stats.inputDrops++;pthread_mutex_unlock(&owner->mutex);return 0;}
 int index=-1;for(int i=0;i<CDV_MAX_PENDING;i++)if(!owner->slots[i].used){index=i;break;}
 if(index<0){pthread_mutex_unlock(&owner->mutex);return -1;}
 uint64_t sequence=++owner->nextSequence;owner->slots[index]=(CDVSlot){sequence,timestamp,true};owner->stats.pending++;owner->stats.submitted++;owner->stats.waitingForKeyframe=0;
 owner->stats.lastInputBytes=size;owner->stats.lastInputTimestamp=timestamp;owner->stats.lastInputKeyframe=key;
 if(owner->stats.pending>owner->stats.maxPending)owner->stats.maxPending=owner->stats.pending;
 pthread_mutex_unlock(&owner->mutex);
 CMBlockBufferRef block=NULL;CMSampleBufferRef sample=NULL;
 uint64_t stage=CDV_STAGE_BLOCK_CREATE;OSStatus status=CMBlockBufferCreateWithMemoryBlock(kCFAllocatorDefault,NULL,size,kCFAllocatorDefault,NULL,0,size,0,&block);
 if(!status){stage=CDV_STAGE_BLOCK_COPY;status=CMBlockBufferReplaceDataBytes(bytes,block,0,size);}
 CMSampleTimingInfo timing={kCMTimeInvalid,CMTimeMake((int64_t)timestamp,1000000),kCMTimeInvalid};size_t sampleSize=size;
 if(!status){stage=CDV_STAGE_SAMPLE_CREATE;status=CMSampleBufferCreateReady(kCFAllocatorDefault,block,owner->format,1,1,&timing,1,&sampleSize,&sample);}
 if(!status){CFArrayRef attachments=CMSampleBufferGetSampleAttachmentsArray(sample,true);if(attachments&&CFArrayGetCount(attachments)){CFMutableDictionaryRef a=(CFMutableDictionaryRef)CFArrayGetValueAtIndex(attachments,0);CFDictionarySetValue(a,kCMSampleAttachmentKey_NotSync,key?kCFBooleanFalse:kCFBooleanTrue);}
  stage=CDV_STAGE_SUBMIT;VTDecodeInfoFlags flags=0;status=VTDecompressionSessionDecodeFrame(owner->session,sample,kVTDecodeFrame_EnableAsynchronousDecompression,(void *)(uintptr_t)sequence,&flags);
  pthread_mutex_lock(&owner->mutex);owner->stats.lastSubmitStatus=status;owner->stats.lastDecodeFlags=flags;pthread_mutex_unlock(&owner->mutex);
  if(!status&&(flags&kVTDecodeInfo_FrameDropped))status=CDV_BAD_FRAME;
 }
 if(sample)CFRelease(sample);if(block)CFRelease(block);if(status){complete_error(owner,sequence,status,stage);return -1;}return 1;
}
int32_t cd_video_latest(void *handle,uint64_t after,uint8_t *output,uint32_t capacity,CDVFrame *frame) {
 CDVideo *owner=handle;if(!owner||!output||!frame||capacity>CDV_MAX_BYTES)return -1;
 pthread_mutex_lock(&owner->mutex);int32_t result=0;
 if(!owner->closing&&owner->jpeg&&owner->latest.sequence>after){if(capacity<owner->latest.size)result=-1;else{*frame=owner->latest;memcpy(output,owner->jpeg,frame->size);result=1;}}
 pthread_mutex_unlock(&owner->mutex);return result;
}
int32_t cd_video_stats(void *handle,CDVStats *stats) {
 CDVideo *owner=handle;if(!owner||!stats)return -1;pthread_mutex_lock(&owner->mutex);*stats=owner->stats;pthread_mutex_unlock(&owner->mutex);return 0;
}
uint32_t cd_video_abi_version(void) {return 2;}
