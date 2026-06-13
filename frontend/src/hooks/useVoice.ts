import { useState, useCallback, useRef } from 'react';
import { startTranscription, stopTranscription, isSupported } from '../services/transcribe';

export type VoiceState = 'idle' | 'recording' | 'processing';

interface UseVoiceReturn {
  isRecording: boolean;
  state: VoiceState;
  startRecording: () => void;
  stopRecording: () => void;
  transcript: string;
  error: string | null;
  supported: boolean;
}

const SILENCE_TIMEOUT_MS = 10_000; // Auto-stop after 10s of silence

/**
 * Hook that manages voice recording state and transcription.
 *
 * - Connects to the Web Speech API transcription service
 * - Auto-stops after 10 seconds of silence
 * - Returns the final transcribed text on stop
 */
export function useVoice(): UseVoiceReturn {
  const [state, setState] = useState<VoiceState>('idle');
  const [transcript, setTranscript] = useState('');
  const [error, setError] = useState<string | null>(null);
  const silenceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const finalTranscriptRef = useRef('');

  const clearSilenceTimer = useCallback(() => {
    if (silenceTimerRef.current) {
      clearTimeout(silenceTimerRef.current);
      silenceTimerRef.current = null;
    }
  }, []);

  const resetSilenceTimer = useCallback(() => {
    clearSilenceTimer();
    silenceTimerRef.current = setTimeout(() => {
      // Auto-stop after silence
      stopTranscription();
      setState('idle');
    }, SILENCE_TIMEOUT_MS);
  }, [clearSilenceTimer]);

  const startRecording = useCallback(() => {
    if (!isSupported()) {
      setError('Speech recognition is not supported in this browser.');
      return;
    }

    setError(null);
    setTranscript('');
    finalTranscriptRef.current = '';
    setState('recording');

    // Start the silence timer immediately
    resetSilenceTimer();

    startTranscription(
      (text, isFinal) => {
        // Reset silence timer on any speech activity
        resetSilenceTimer();

        if (isFinal) {
          // Accumulate final results
          finalTranscriptRef.current = finalTranscriptRef.current
            ? `${finalTranscriptRef.current} ${text}`
            : text;
          setTranscript(finalTranscriptRef.current);
        } else {
          // Show interim results alongside any accumulated finals
          const display = finalTranscriptRef.current
            ? `${finalTranscriptRef.current} ${text}`
            : text;
          setTranscript(display);
        }
      },
      (errorMessage) => {
        clearSilenceTimer();
        setError(errorMessage);
        setState('idle');
      },
    );
  }, [resetSilenceTimer, clearSilenceTimer]);

  const stopRecording = useCallback(() => {
    clearSilenceTimer();
    stopTranscription();
    setState('idle');
  }, [clearSilenceTimer]);

  return {
    isRecording: state === 'recording',
    state,
    startRecording,
    stopRecording,
    transcript,
    error,
    supported: isSupported(),
  };
}
