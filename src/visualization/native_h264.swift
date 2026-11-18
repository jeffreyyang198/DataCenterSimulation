// Installed macOS AVFoundation fallback when FFmpeg is unavailable.
// Reads packed BGRA frames from Python; emits standard H.264/AVC MP4.
import Foundation
import AVFoundation
import CoreVideo
import VideoToolbox
import ImageIO

func fail(_ message: String) -> Never {
    FileHandle.standardError.write(Data((message + "\n").utf8)); exit(1)
}

func readExact(_ size: Int) throws -> Data {
    var result = Data(); result.reserveCapacity(size)
    while result.count < size {
        guard let part = try FileHandle.standardInput.read(upToCount: size-result.count), !part.isEmpty else {
            fail("Unexpected end of BGRA frame stream")
        }
        result.append(part)
    }
    return result
}

func savePNG(_ buffer: CVPixelBuffer, _ path: String) {
    var image: CGImage?
    guard VTCreateCGImageFromCVPixelBuffer(buffer, options: nil, imageOut: &image) == noErr,
          let image = image,
          let destination = CGImageDestinationCreateWithURL(URL(fileURLWithPath:path) as CFURL,"public.png" as CFString,1,nil) else {
        fail("Could not render decoded video frame")
    }
    CGImageDestinationAddImage(destination,image,nil)
    if !CGImageDestinationFinalize(destination) { fail("PNG write failed") }
}

let args=Array(CommandLine.arguments.dropFirst())
guard !args.isEmpty else { fail("encode output width height fps frames | verify video report") }
do {
    if args[0] == "encode" {
        guard args.count == 7, let width=Int(args[2]), let height=Int(args[3]),
              let fps=Int32(args[4]), let frames=Int(args[5]), let bitrate=Int(args[6]) else { fail("Invalid encoder arguments") }
        let url=URL(fileURLWithPath:args[1])
        let writer=try AVAssetWriter(outputURL:url,fileType:.mp4)
        writer.shouldOptimizeForNetworkUse=true
        let settings:[String:Any]=[
            AVVideoCodecKey:AVVideoCodecType.h264, AVVideoWidthKey:width, AVVideoHeightKey:height,
            AVVideoCompressionPropertiesKey:[AVVideoAverageBitRateKey:bitrate,
                AVVideoProfileLevelKey:AVVideoProfileLevelH264MainAutoLevel,
                AVVideoMaxKeyFrameIntervalKey:Int(fps)*2,AVVideoAllowFrameReorderingKey:false]
        ]
        let input=AVAssetWriterInput(mediaType:.video,outputSettings:settings)
        input.expectsMediaDataInRealTime=false
        let attributes:[String:Any]=[kCVPixelBufferPixelFormatTypeKey as String:kCVPixelFormatType_32BGRA,
            kCVPixelBufferWidthKey as String:width,kCVPixelBufferHeightKey as String:height,
            kCVPixelBufferIOSurfacePropertiesKey as String:[:]]
        let adaptor=AVAssetWriterInputPixelBufferAdaptor(assetWriterInput:input,sourcePixelBufferAttributes:attributes)
        guard writer.canAdd(input) else { fail("H.264 writer input unavailable") }
        writer.add(input)
        guard writer.startWriting() else { fail("H.264 start failed: \(String(describing:writer.error))") }
        writer.startSession(atSourceTime:.zero)
        for index in 0..<frames {
            let data=try readExact(width*height*4)
            while !input.isReadyForMoreMediaData {
                if writer.status == .failed { fail("H.264 encoder failed: \(String(describing:writer.error))") }
                Thread.sleep(forTimeInterval:0.002)
            }
            try autoreleasepool {
                var pixel:CVPixelBuffer?
                let status=CVPixelBufferCreate(kCFAllocatorDefault,width,height,kCVPixelFormatType_32BGRA,attributes as CFDictionary,&pixel)
                guard status == kCVReturnSuccess, let pixel=pixel else { fail("Pixel-buffer allocation failed") }
                CVPixelBufferLockBaseAddress(pixel,[])
                let stride=CVPixelBufferGetBytesPerRow(pixel)
                let destination=CVPixelBufferGetBaseAddress(pixel)!
                data.withUnsafeBytes { source in
                    for row in 0..<height {
                        memcpy(destination.advanced(by:row*stride),source.baseAddress!.advanced(by:row*width*4),width*4)
                    }
                }
                CVPixelBufferUnlockBaseAddress(pixel,[])
                guard adaptor.append(pixel,withPresentationTime:CMTime(value:Int64(index),timescale:fps)) else {
                    fail("Could not append frame \(index): \(String(describing:writer.error))")
                }
            }
        }
        input.markAsFinished()
        let semaphore=DispatchSemaphore(value:0)
        writer.finishWriting { semaphore.signal() }
        semaphore.wait()
        guard writer.status == .completed else { fail("H.264 finalization failed: \(String(describing:writer.error))") }
        print("H.264 MP4 encoded: \(frames) frames")
    } else if args[0] == "verify" {
        guard args.count == 3 else { fail("verify requires video and report paths") }
        let asset=AVURLAsset(url:URL(fileURLWithPath:args[1]))
        guard let track=asset.tracks(withMediaType:.video).first else { fail("Export has no video track") }
        let reader=try AVAssetReader(asset:asset)
        let output=AVAssetReaderTrackOutput(track:track,outputSettings:[kCVPixelBufferPixelFormatTypeKey as String:kCVPixelFormatType_32BGRA])
        output.alwaysCopiesSampleData=false
        reader.add(output)
        guard reader.startReading() else { fail("Cannot open/decode MP4: \(String(describing:reader.error))") }
        var count=0
        let duration=CMTimeGetSeconds(asset.duration)
        let nominal=Double(track.nominalFrameRate)
        let expected=Int((duration*nominal).rounded())
        while let sample=output.copyNextSampleBuffer() {
            if (count==0 || count==expected/2 || count==expected-1), let buffer=CMSampleBufferGetImageBuffer(sample) {
                savePNG(buffer,args[2]+".frame_\(count).png")
            }
            count += 1
        }
        guard reader.status == .completed else { fail("MP4 decode did not finish: \(String(describing:reader.error))") }
        let format=track.formatDescriptions.first as! CMFormatDescription
        let subtype=CMFormatDescriptionGetMediaSubType(format)
        let bytes:[UInt8]=[UInt8((subtype>>24)&255),UInt8((subtype>>16)&255),UInt8((subtype>>8)&255),UInt8(subtype&255)]
        let codec=String(bytes:bytes,encoding:.ascii) ?? "unknown"
        guard codec=="avc1" else { fail("Expected H.264/AVC, found \(codec)") }
        let report:[String:Any]=["codec":codec,"width":Int(track.naturalSize.width),"height":Int(track.naturalSize.height),
            "fps":nominal,"duration_seconds":duration,"decoded_frames":count,"status":"passed"]
        let data=try JSONSerialization.data(withJSONObject:report,options:[.prettyPrinted,.sortedKeys])
        try data.write(to:URL(fileURLWithPath:args[2]))
        print(String(data:data,encoding:.utf8)!)
    } else { fail("Unknown mode") }
} catch { fail(String(describing:error)) }
