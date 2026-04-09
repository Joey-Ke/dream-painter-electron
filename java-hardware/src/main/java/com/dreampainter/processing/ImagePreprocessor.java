package com.dreampainter.processing;

import javax.imageio.ImageIO;
import java.awt.*;
import java.awt.image.BufferedImage;
import java.awt.image.ColorConvertOp;
import java.awt.image.RescaleOp;
import java.io.File;
import java.io.IOException;
import java.nio.file.Path;

/**
 * 集中实现当前阶段的「AI 识别友好型」图像预处理。
 *
 * 目标：让图片更容易被后续 AI 准确识别，而不是视觉美化。
 * 核心步骤（第一版）：
 * - 统一输出尺寸（带简单 letterbox，尽量保持主体比例）
 * - 可选灰度化（便于后续只关注结构与纹理）
 * - 适度的亮度 / 对比度增强（稳定曝光和对比）
 */
public class ImagePreprocessor {

    // 为后续识别准备的统一输出尺寸（可根据后端模型要求再调整）
    private final int targetWidth;
    private final int targetHeight;

    public ImagePreprocessor() {
        this(512, 512);
    }

    public ImagePreprocessor(int targetWidth, int targetHeight) {
        this.targetWidth = targetWidth;
        this.targetHeight = targetHeight;
    }

    /**
     * 端到端预处理：读取原图、执行预处理、保存为新文件。
     *
     * @param originalFile       原始图片文件
     * @param processedOutputPath 处理后输出路径
     * @param enableGrayscale    是否启用灰度化
     * @return 处理后图片文件
     */
    public File preprocessAndSave(File originalFile, Path processedOutputPath, boolean enableGrayscale)
            throws IOException {
        System.out.println("[Preprocess] Loading original image from: " + originalFile.getAbsolutePath());
        BufferedImage input = ImageIO.read(originalFile);
        if (input == null) {
            throw new IOException("Failed to read image from file: " + originalFile);
        }

        System.out.println("[Preprocess] Original size: " + input.getWidth() + "x" + input.getHeight());

        BufferedImage processed = preprocessForRecognition(input, enableGrayscale);

        File outFile = processedOutputPath.toFile();
        File parent = outFile.getParentFile();
        if (parent != null && !parent.exists() && !parent.mkdirs() && !parent.exists()) {
            throw new IOException("Failed to create directories: " + parent);
        }

        ImageIO.write(processed, "png", outFile);
        System.out.println("[Preprocess] Processed image saved to: " + outFile.getAbsolutePath());

        return outFile;
    }

    /**
     * 针对 AI 识别的最小预处理流水线。
     */
    public BufferedImage preprocessForRecognition(BufferedImage input, boolean enableGrayscale) {
        BufferedImage current = input;

        current = resizeForRecognition(current);

        current = toGrayscaleIfNeeded(current, enableGrayscale);

        current = enhanceContrastAndBrightness(current);

        // 预留后续步骤：轻量降噪 / 锐化（当前不做复杂卷积，先保持为 no-op）
        // current = denoiseLight(current);
        // current = sharpenLight(current);

        return current;
    }

    /**
     * 统一输出尺寸：尽量保持主体比例，采用简单 letterbox 到 targetWidth x targetHeight。
     */
    public BufferedImage resizeForRecognition(BufferedImage input) {
        int srcW = input.getWidth();
        int srcH = input.getHeight();

        if (srcW == targetWidth && srcH == targetHeight) {
            System.out.println("[Preprocess] Resize: already at target size " + targetWidth + "x" + targetHeight);
            return input;
        }

        double scale = Math.min((double) targetWidth / srcW, (double) targetHeight / srcH);
        int newW = (int) Math.round(srcW * scale);
        int newH = (int) Math.round(srcH * scale);

        System.out.println("[Preprocess] Resize: " + srcW + "x" + srcH +
                " -> scaled " + newW + "x" + newH +
                " -> letterbox to " + targetWidth + "x" + targetHeight);

        BufferedImage scaled = new BufferedImage(newW, newH, BufferedImage.TYPE_INT_RGB);
        Graphics2D gScaled = scaled.createGraphics();
        try {
            gScaled.setRenderingHint(RenderingHints.KEY_INTERPOLATION, RenderingHints.VALUE_INTERPOLATION_BILINEAR);
            gScaled.setRenderingHint(RenderingHints.KEY_RENDERING, RenderingHints.VALUE_RENDER_QUALITY);
            gScaled.setRenderingHint(RenderingHints.KEY_ANTIALIASING, RenderingHints.VALUE_ANTIALIAS_ON);
            gScaled.drawImage(input, 0, 0, newW, newH, null);
        } finally {
            gScaled.dispose();
        }

        BufferedImage output = new BufferedImage(targetWidth, targetHeight, BufferedImage.TYPE_INT_RGB);
        Graphics2D g = output.createGraphics();
        try {
            // 使用中性灰色作为填充，减少对后续识别的干扰
            g.setColor(new Color(128, 128, 128));
            g.fillRect(0, 0, targetWidth, targetHeight);

            int x = (targetWidth - newW) / 2;
            int y = (targetHeight - newH) / 2;
            g.drawImage(scaled, x, y, null);
        } finally {
            g.dispose();
        }

        return output;
    }

    /**
     * 可选灰度化：对于很多识别任务，只保留亮度信息更有利于模型聚焦结构。
     */
    public BufferedImage toGrayscaleIfNeeded(BufferedImage input, boolean enableGrayscale) {
        if (!enableGrayscale) {
            System.out.println("[Preprocess] Grayscale: disabled, keep original color.");
            return input;
        }

        System.out.println("[Preprocess] Grayscale: converting to grayscale.");

        BufferedImage gray = new BufferedImage(input.getWidth(), input.getHeight(), BufferedImage.TYPE_BYTE_GRAY);
        ColorConvertOp op = new ColorConvertOp(input.getColorModel().getColorSpace(),
                gray.getColorModel().getColorSpace(), null);
        op.filter(input, gray);
        return gray;
    }

    /**
     * 适度增强亮度和对比度：稳定曝光，使主体更清晰。
     */
    public BufferedImage enhanceContrastAndBrightness(BufferedImage input) {
        // 适中的对比度和亮度调整系数，可根据后续模型效果再微调
        float contrast = 1.1f;  // >1 提升对比度
        float brightness = 5f;  // 常量偏移，调高整体亮度

        System.out.println("[Preprocess] Enhance: applying contrast=" + contrast + ", brightness=" + brightness);

        RescaleOp rescaleOp = new RescaleOp(contrast, brightness, null);
        BufferedImage dest = new BufferedImage(input.getWidth(), input.getHeight(), input.getType());
        rescaleOp.filter(input, dest);
        return dest;
    }

    // 预留：轻量降噪（当前版本不做复杂卷积处理）
    @SuppressWarnings("unused")
    private BufferedImage denoiseLight(BufferedImage input) {
        System.out.println("[Preprocess] Denoise: skipped in current minimal version.");
        return input;
    }

    // 预留：轻量锐化（当前版本不做复杂卷积处理）
    @SuppressWarnings("unused")
    private BufferedImage sharpenLight(BufferedImage input) {
        System.out.println("[Preprocess] Sharpen: skipped in current minimal version.");
        return input;
    }
}

