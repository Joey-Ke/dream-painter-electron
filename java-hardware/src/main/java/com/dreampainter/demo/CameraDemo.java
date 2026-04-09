package com.dreampainter.demo;

import com.dreampainter.camera.CameraDevice;
import com.dreampainter.camera.CameraService;
import com.dreampainter.camera.JavaCvCameraManager;
import com.dreampainter.capture.SnapshotService;
import com.dreampainter.processing.ImagePreprocessor;
import org.bytedeco.javacv.FrameGrabber;

import java.io.File;
import java.nio.file.Paths;
import java.util.List;

/**
 * 本地运行的 JavaCV 摄像头最小 demo。
 *
 * 目标能力：
 * 1. 枚举本机摄像头
 * 2. 打开指定摄像头
 * 3. 持续抓帧
 * 4. 抓拍一张并保存到本地
 * 5. 关闭摄像头并释放资源
 */
public class CameraDemo {

    // 外接摄像头优先匹配的名称关键词
    private static final String PREFERRED_CAMERA_KEYWORD = "UGREEN";
    // 如果找不到匹配关键词的设备，则回退到该索引
    private static final int FALLBACK_CAMERA_INDEX = 1;

    public static void main(String[] args) {
        JavaCvCameraManager cameraManager = new JavaCvCameraManager();
        CameraService cameraService = new CameraService(cameraManager);
        SnapshotService snapshotService = new SnapshotService(cameraManager);
        ImagePreprocessor imagePreprocessor = new ImagePreprocessor();

        try {
            // 1. 枚举本机摄像头
            System.out.println("Listing available cameras...");
            List<CameraDevice> cameras = cameraService.listCameras();
            if (cameras.isEmpty()) {
                System.out.println("No cameras found.");
                return;
            }
            for (CameraDevice device : cameras) {
                System.out.println("Found camera: index=" + device.getIndex() + ", name=" + device.getName());
            }

            // 2. 按名称关键词优先选择摄像头（例如 UGREEN），否则回退到指定 index
            System.out.println("Selecting camera by keyword \"" + PREFERRED_CAMERA_KEYWORD +
                    "\" or fallback index " + FALLBACK_CAMERA_INDEX + "...");
            int openedIndex = cameraService.openCameraByKeywordOrIndex(PREFERRED_CAMERA_KEYWORD, FALLBACK_CAMERA_INDEX);
            if (openedIndex < 0) {
                System.out.println("No camera opened.");
                return;
            }
            System.out.println("Camera opened at index " + openedIndex + ".");

            // 3. 持续抓帧（例如持续 3 秒，每 200ms 抓一帧）
            System.out.println("Starting continuous capture for 3 seconds...");
            cameraService.continuousCapture(3000L, 200L);

            // 4. 抓拍一张并保存原始图片
            System.out.println("Taking snapshot...");
            File original = snapshotService.takeSnapshot(Paths.get("camera-original.png"));
            System.out.println("Original snapshot saved to: " + original.getAbsolutePath());

            // 5. 对原始图片执行 AI 识别友好型预处理，并保存处理后图片
            System.out.println("Running image preprocessing for AI-friendly recognition...");
            boolean enableGrayscale = true; // 保留简单开关，后续可根据识别任务调整
            File processed = imagePreprocessor.preprocessAndSave(
                    original,
                    Paths.get("camera-processed.png"),
                    enableGrayscale
            );
            System.out.println("Processed image saved to: " + processed.getAbsolutePath());

            // 6. 关闭摄像头并释放资源
            System.out.println("Closing camera...");
            cameraService.closeCamera();
            System.out.println("Done.");
        } catch (FrameGrabber.Exception e) {
            System.err.println("Camera / JavaCV error: " + e.getMessage());
            e.printStackTrace();
        } catch (Exception e) {
            System.err.println("Unexpected error: " + e.getMessage());
            e.printStackTrace();
        } finally {
            // 确保资源释放
            try {
                cameraService.closeCamera();
            } catch (Exception ignore) {
            }
        }
    }
}

