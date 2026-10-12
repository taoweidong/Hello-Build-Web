// utils/screenshot 单测：报告截图 dataURL 纯函数（R3-F8 抽取，边界锁定）
import { describe, expect, it } from "vitest";
import { base64Bytes, dataUrlToBlob } from "@/utils/screenshot";

describe("base64Bytes 体积估算", () => {
  it("dataURL 主体 4 字符 ≈ 3 字节（估算不扣除 = 填充，偏大方向安全）", () => {
    // "QUJD" 为 "ABC"（3 字节）的 base64，无填充：估算精确
    expect(base64Bytes("data:image/png;base64,QUJD")).toBe(3);
    // "QUJDRA==" 为 "ABCD"（4 字节）的 base64：主体 8 字符 → 8*0.75=6，
    // 估算含填充字符略大于真实体积（用于 2MB 上限判断，偏大方向安全）
    expect(base64Bytes("data:image/png;base64,QUJDRA==")).toBe(6);
  });

  it("空主体返回 0", () => {
    expect(base64Bytes("data:image/png;base64,")).toBe(0);
  });

  it("无逗号 dataURL / 空串返回 0 而非 NaN", () => {
    expect(base64Bytes("data:image/png;base64")).toBe(0);
    expect(base64Bytes("")).toBe(0);
  });
});

describe("dataUrlToBlob 转换", () => {
  it("解析 mime 与字节内容", () => {
    const blob = dataUrlToBlob("data:image/jpeg;base64,QUJDRA==");
    expect(blob.type).toBe("image/jpeg");
    expect(blob.size).toBe(4);
  });

  it("mime 缺失兜底 image/png", () => {
    // head 无 ";" 时正则不命中，兜底 image/png
    expect(dataUrlToBlob("data:base64,QUJD").type).toBe("image/png");
    expect(dataUrlToBlob("data:;base64,QUJD").type).toBe("image/png");
  });

  it("空主体返回空 Blob 不抛异常", () => {
    const blob = dataUrlToBlob("data:image/png;base64,");
    expect(blob.size).toBe(0);
    expect(blob.type).toBe("image/png");
  });

  it("无逗号 dataURL 返回空 Blob（mime 兜底 image/png）不抛异常", () => {
    const blob = dataUrlToBlob("no-comma");
    expect(blob.size).toBe(0);
    expect(blob.type).toBe("image/png");
  });
});
