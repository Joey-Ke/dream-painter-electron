package com.dreampainter.capture;

import com.dreampainter.camera.JavaCvCameraManager;
import org.bytedeco.javacv.Frame;
import org.bytedeco.javacv.FrameGrabber;
import org.bytedeco.javacv.Java2DFrameConverter;

import javax.imageio.ImageIO;
import java.awt.image.BufferedImage;
import java.io.File;
import java.io.IOException;
import java.nio.file.Path;

/**
 * 负责从当前打开的摄像头抓拍一张并保存到本地。
 */
public class SnapshotService {

    private final JavaCvCameraManager cameraManager;

    public SnapshotService(JavaCvCameraManager cameraManager) {
        this.cameraManager = cameraManager;
    }

    /**
     * 抓拍一张并保存为 PNG。
     *
     * @param outputPath 输出文件路径
     * @return 实际保存的文件
     */
    public File takeSnapshot(Path outputPath) throws FrameGrabber.Exception, IOException {
        Frame frame = cameraManager.grabFrame();
        if (frame == null) {
            throw new IllegalStateException("Failed to grab frame for snapshot.");
        }

        try (Java2DFrameConverter converter = new Java2DFrameConverter()) {
            BufferedImage image = converter.convert(frame);
            if (image == null) {
                throw new IllegalStateException("Converted image is null.");
            }
            File file = outputPath.toFile();
            File parent = file.getParentFile();
            if (parent != null && !parent.exists()) {
                if (!parent.mkdirs() && !parent.exists()) {
                    throw new IOException("Failed to create directories: " + parent);
                }
            }
            ImageIO.write(image, "png", file);
            return file;
        }
    }
}

