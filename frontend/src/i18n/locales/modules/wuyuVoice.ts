import type { TranslationDict } from "../../types";

/** 语音输入（教师语音录入 P0）中文翻译 — 成长记录内容语音转写 */
export const wuyuVoiceZh: TranslationDict = {
  "voice.button": "语音输入",
  "voice.start": "点击开始录音",
  "voice.stop": "停止录音",
  "voice.recording": "录音中",
  "voice.recognizing": "转写中…",
  "voice.fail": "语音转写失败，请重试或手动输入",
  "voice.success": "已识别语音内容并填入",
  "voice.unsupported": "当前浏览器不支持语音输入",
  "voice.denied": "未获得麦克风权限，请在浏览器设置中允许后重试",
};

/** 语音输入（教师语音录入 P0）英文翻译 */
export const wuyuVoiceEn: TranslationDict = {
  "voice.button": "Voice input",
  "voice.start": "Click to start recording",
  "voice.stop": "Stop recording",
  "voice.recording": "Recording",
  "voice.recognizing": "Transcribing…",
  "voice.fail": "Transcription failed. Please retry or type manually.",
  "voice.success": "Recognized text inserted",
  "voice.unsupported": "Voice input is not supported in this browser",
  "voice.denied": "Microphone access was denied. Please allow it in browser settings and retry.",
};
