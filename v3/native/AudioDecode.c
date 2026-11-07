// SPDX-License-Identifier: GPL-3.0-only
// Raw AAC-LC access units -> interleaved S16LE. No file/network/audio output.
#include <AudioToolbox/AudioToolbox.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

enum { CD_AAC_MAX_PACKET = 8192, CD_AAC_MAX_FRAMES = 8192 };
enum { CD_AAC_BAD_ARGUMENT = -70001, CD_AAC_NO_MEMORY = -70002,
       CD_AAC_BAD_OUTPUT = -70003, CD_AAC_NOT_CONSUMED = -70004,
       CD_AAC_CLOSED_STREAM = -70005 };
// Apple documents a custom callback error for a temporary input shortage.
// The converter delivers pending PCM without interpreting this as end-of-stream.
static const OSStatus CD_AAC_NEED_INPUT = 0x63646e69; /* cdni */

typedef struct {
    AudioConverterRef converter;
    UInt32 channels;
    uint8_t *held;
    AudioStreamPacketDescription description;
    bool ended;
    OSStatus failed;
} CDAAC;

typedef struct {
    CDAAC *decoder;
    uint8_t *incoming;
    UInt32 size;
    bool supplied;
    bool eof;
} CDAACInput;

static OSStatus input_packet(AudioConverterRef converter, UInt32 *packets,
                             AudioBufferList *buffers,
                             AudioStreamPacketDescription **descriptions,
                             void *opaque) {
    (void)converter;
    CDAACInput *input = (CDAACInput *)opaque;
    CDAAC *decoder = input->decoder;
    // AudioConverter's input data must remain valid until the NEXT callback.
    // The owned copy also covers implementations retaining it across Fill calls.
    free(decoder->held);
    decoder->held = NULL;
    buffers->mNumberBuffers = 1;
    buffers->mBuffers[0].mNumberChannels = decoder->channels;
    if (!input->incoming || input->supplied) {
        *packets = 0;
        buffers->mBuffers[0].mDataByteSize = 0;
        buffers->mBuffers[0].mData = NULL;
        if (descriptions) *descriptions = NULL;
        return input->eof ? noErr : CD_AAC_NEED_INPUT;
    }
    decoder->held = input->incoming;
    input->incoming = NULL;
    input->supplied = true;
    *packets = 1;
    buffers->mBuffers[0].mDataByteSize = input->size;
    buffers->mBuffers[0].mData = decoder->held;
    decoder->description.mStartOffset = 0;
    decoder->description.mDataByteSize = input->size;
    decoder->description.mVariableFramesInPacket = 1024;
    if (descriptions) *descriptions = &decoder->description;
    return noErr;
}

void *cd_aac_create(uint32_t rate, uint32_t channels, int32_t *error) {
    if (error) *error = CD_AAC_BAD_ARGUMENT;
    if ((rate != 44100 && rate != 48000) || (channels != 1 && channels != 2)) return NULL;
    CDAAC *decoder = calloc(1, sizeof(*decoder));
    if (!decoder) { if (error) *error = CD_AAC_NO_MEMORY; return NULL; }
    decoder->channels = channels;
    AudioStreamBasicDescription source = {0}, target = {0};
    source.mSampleRate = rate;
    source.mFormatID = kAudioFormatMPEG4AAC;
    source.mFormatFlags = kMPEG4Object_AAC_LC;
    source.mChannelsPerFrame = channels;
    source.mFramesPerPacket = 1024;
    target.mSampleRate = rate;
    target.mFormatID = kAudioFormatLinearPCM;
    target.mFormatFlags = kLinearPCMFormatFlagIsSignedInteger | kLinearPCMFormatFlagIsPacked;
    target.mChannelsPerFrame = channels;
    target.mBitsPerChannel = 16;
    target.mFramesPerPacket = 1;
    target.mBytesPerFrame = target.mBytesPerPacket = channels * 2;
    // The software decoder avoids exclusive hardware codec/session ownership.
    // 'appl' is named kAppleSoftwareAudioCodecManufacturer in the iPhone SDK;
    // the same codec manufacturer is present on macOS without that enum name.
    AudioClassDescription codec = {kAudioDecoderComponentType, kAudioFormatMPEG4AAC,
                                   0x6170706c};
    OSStatus status = AudioConverterNewSpecific(&source, &target, 1, &codec, &decoder->converter);
    if (!status) {
        // ISO AudioSpecificConfig: AAC-LC (2), indexed sample rate, channel config.
        // AudioConverter's cookie is an MPEG-4 ES descriptor containing that
        // two-byte configuration, not the bare two bytes (macOS rejects those).
        unsigned index = rate == 44100 ? 4 : 3;
        uint16_t config = (uint16_t)((2u << 11) | (index << 7) | (channels << 3));
        uint8_t cookie[] = {
            3,25,0,0,0,                 // ES_Descriptor, ES_ID, flags
            4,17,0x40,0x15,             // DecoderConfig: MPEG-4 audio stream
            0,0,0,0,0,0,0,0,0,0,0,    // buffer size, maximum/average bitrate
            5,2,(uint8_t)(config >> 8),(uint8_t)config,
            6,1,2                      // SLConfig predefined MPEG-4
        };
        status = AudioConverterSetProperty(decoder->converter,
                 kAudioConverterDecompressionMagicCookie, sizeof(cookie), cookie);
    }
    if (!status) {
        UInt32 prime = kConverterPrimeMethod_None;
        OSStatus prime_status = AudioConverterSetProperty(decoder->converter,
                                  kAudioConverterPrimeMethod, sizeof(prime), &prime);
        if (prime_status != noErr && prime_status != kAudioConverterErr_PropertyNotSupported)
            status = prime_status;
    }
    if (status) {
        if (decoder->converter) AudioConverterDispose(decoder->converter);
        free(decoder);
        if (error) *error = status;
        return NULL;
    }
    if (error) *error = noErr;
    return decoder;
}

static int32_t convert(CDAAC *decoder, const uint8_t *packet, uint32_t size,
                       int16_t *output, uint32_t capacity_frames,
                       uint32_t *output_frames, bool eof) {
    if (output_frames) *output_frames = 0;
    if (!decoder || !output || !output_frames || !capacity_frames ||
        capacity_frames > CD_AAC_MAX_FRAMES ||
        (!eof && (!packet || !size || size > CD_AAC_MAX_PACKET))) return CD_AAC_BAD_ARGUMENT;
    if (decoder->failed) return decoder->failed;
    if (!eof && decoder->ended) return CD_AAC_CLOSED_STREAM;
    CDAACInput input = {.decoder = decoder, .size = size, .eof = eof};
    if (!eof) {
        input.incoming = malloc(size);
        if (!input.incoming) return CD_AAC_NO_MEMORY;
        memcpy(input.incoming, packet, size);
    }
    UInt32 bytes = capacity_frames * decoder->channels * 2;
    memset(output, 0, bytes);
    AudioBufferList result = {.mNumberBuffers = 1};
    result.mBuffers[0].mNumberChannels = decoder->channels;
    result.mBuffers[0].mDataByteSize = bytes;
    result.mBuffers[0].mData = output;
    UInt32 frames = capacity_frames;
    OSStatus status = AudioConverterFillComplexBuffer(decoder->converter, input_packet,
                                &input, &frames, &result, NULL);
    free(input.incoming);
    if (status == CD_AAC_NEED_INPUT) status = noErr;
    if (!status && !eof && !input.supplied) status = CD_AAC_NOT_CONSUMED;
    if (!status && (frames > capacity_frames || result.mNumberBuffers != 1 ||
        result.mBuffers[0].mData != output ||
        result.mBuffers[0].mDataByteSize != frames * decoder->channels * 2))
        status = CD_AAC_BAD_OUTPUT;
    if (status) { decoder->failed = status; return status; }
    decoder->ended = eof;
    *output_frames = frames;
    return noErr;
}

int32_t cd_aac_decode(void *handle, const uint8_t *packet, uint32_t size,
                      int16_t *output, uint32_t capacity_frames, uint32_t *output_frames) {
    return convert((CDAAC *)handle, packet, size, output, capacity_frames, output_frames, false);
}

int32_t cd_aac_flush(void *handle, int16_t *output, uint32_t capacity_frames,
                     uint32_t *output_frames) {
    return convert((CDAAC *)handle, NULL, 0, output, capacity_frames, output_frames, true);
}

int32_t cd_aac_reset(void *handle) {
    CDAAC *decoder = (CDAAC *)handle;
    if (!decoder) return CD_AAC_BAD_ARGUMENT;
    OSStatus status = AudioConverterReset(decoder->converter);
    if (!status) {
        free(decoder->held); decoder->held = NULL;
        decoder->ended = false; decoder->failed = noErr;
    }
    return status;
}

void cd_aac_destroy(void *handle) {
    CDAAC *decoder = (CDAAC *)handle;
    if (!decoder) return;
    AudioConverterDispose(decoder->converter);
    free(decoder->held);
    memset(decoder, 0, sizeof(*decoder));
    free(decoder);
}
