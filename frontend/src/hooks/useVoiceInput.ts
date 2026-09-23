/**
 * 语音输入 hook — 教师语音录入 P0。
 *
 * 封装 MediaRecorder 录音（开始/停止/计时）+ 上传后端 ASR + 返回识别文字。
 * 浏览器不支持 MediaRecorder / getUserMedia 时返回 supported=false，UI 可隐藏按钮。
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { asrTranscribe } from "@/services/asrApi";

export type VoiceState = "idle" | "recording" | "recognizing" | "unsupported";
export type VoiceError = "" | "denied" | "error";

export interface UseVoiceInputResult {
  /** 当前语音输入状态 */
  state: VoiceState;
  /** 录音秒数（recording 时有效） */
  seconds: number;
  /** 错误码：denied=未授权麦克风，error=转写/录音出错 */
  error: VoiceError;
  /** 当前环境是否支持语音输入 */
  supported: boolean;
  /** 开始录音（请求麦克风权限）。返回错误码：""=已开始，denied=未授权，error=不支持 */
  start: () => Promise<VoiceError>;
  /** 停止录音并上传转写，返回识别文字（失败返回 null） */
  stopAndTranscribe: () => Promise<string | null>;
  /** 取消录音，丢弃已录内容 */
  cancel: () => void;
}

/** 当前浏览器是否具备录音能力 */
function canRecord(): boolean {
  if (typeof window === "undefined") return false;
  return (
    typeof window.MediaRecorder !== "undefined" &&
    Boolean(navigator.mediaDevices?.getUserMedia)
  );
}

/** 挑选浏览器最支持的音频容器 */
function pickMimeType(): string | null {
  if (typeof window === "undefined" || typeof window.MediaRecorder === "undefined") {
    return null;
  }
  const candidates = [
    "audio/webm;codecs=opus",
    "audio/webm",
    "audio/ogg;codecs=opus",
    "audio/ogg",
    "audio/mp4",
    "audio/mpeg",
  ];
  for (const mime of candidates) {
    try {
      if (window.MediaRecorder.isTypeSupported(mime)) return mime;
    } catch {
      // 个别实现可能抛错，跳过
    }
  }
  return null;
}

export function useVoiceInput(): UseVoiceInputResult {
  const [state, setState] = useState<VoiceState>(
    canRecord() ? "idle" : "unsupported"
  );
  const [seconds, setSeconds] = useState(0);
  const [error, setError] = useState<VoiceError>("");

  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const clearTimer = useCallback(() => {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
    setSeconds(0);
  }, []);

  const stopStream = useCallback(() => {
    const stream = streamRef.current;
    if (stream) {
      stream.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    }
  }, []);

  const cancel = useCallback(() => {
    const recorder = recorderRef.current;
    if (recorder && recorder.state !== "inactive") {
      try {
        recorder.onstop = null;
        recorder.stop();
      } catch {
        // ignore
      }
    }
    recorderRef.current = null;
    chunksRef.current = [];
    stopStream();
    clearTimer();
    setState("idle");
    setError("");
  }, [stopStream, clearTimer]);

  const start = useCallback(async (): Promise<VoiceError> => {
    if (!canRecord()) {
      setState("unsupported");
      setError("error");
      return "error";
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mime = pickMimeType();
      const recorder = mime
        ? new MediaRecorder(stream, { mimeType: mime })
        : new MediaRecorder(stream);
      recorderRef.current = recorder;
      streamRef.current = stream;
      chunksRef.current = [];

      recorder.ondataavailable = (e: BlobEvent) => {
        if (e.data && e.data.size > 0) chunksRef.current.push(e.data);
      };
      recorder.onerror = () => {
        cancel();
        setError("error");
      };

      recorder.start();
      setState("recording");
      setError("");
      const startedAt = Date.now();
      clearTimer();
      timerRef.current = setInterval(() => {
        setSeconds(Math.floor((Date.now() - startedAt) / 1000));
      }, 1000);
      return "";
    } catch {
      stopStream();
      setState("idle");
      setError("denied");
      return "denied";
    }
  }, [stopStream, clearTimer, cancel]);

  const stopAndTranscribe = useCallback(async (): Promise<string | null> => {
    const recorder = recorderRef.current;
    if (!recorder || recorder.state === "inactive") return null;

    const blob = await new Promise<Blob>((resolve) => {
      recorder.onstop = () => {
        const type = recorder.mimeType || "audio/webm";
        resolve(new Blob(chunksRef.current, { type }));
      };
      recorder.stop();
      stopStream();
    });
    recorderRef.current = null;
    chunksRef.current = [];
    clearTimer();

    setState("recognizing");
    try {
      const text = await asrTranscribe(blob);
      setState("idle");
      setError("");
      return text || null;
    } catch {
      setState("idle");
      setError("error");
      return null;
    }
  }, [stopStream, clearTimer]);

  // 组件卸载时清理录音资源
  useEffect(() => {
    return () => {
      clearTimer();
      const recorder = recorderRef.current;
      if (recorder && recorder.state !== "inactive") {
        try {
          recorder.stop();
        } catch {
          // ignore
        }
      }
      stopStream();
    };
  }, [clearTimer, stopStream]);

  return {
    state,
    seconds,
    error,
    supported: state !== "unsupported",
    start,
    stopAndTranscribe,
    cancel,
  };
}
