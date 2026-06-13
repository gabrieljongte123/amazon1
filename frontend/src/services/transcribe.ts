/**
 * Transcription service using Web Speech API (SpeechRecognition).
 *
 * For the hackathon prototype we use the browser-native SpeechRecognition API
 * which works in Chrome/Edge without any AWS credentials. A production version
 * would swap this for Amazon Transcribe WebSocket streaming.
 */

// Browser compatibility types
interface SpeechRecognitionEvent {
  results: SpeechRecognitionResultList;
  resultIndex: number;
}

interface SpeechRecognitionErrorEvent {
  error: string;
  message: string;
}

type OnResultCallback = (transcript: string, isFinal: boolean) => void;
type OnErrorCallback = (error: string) => void;

let recognition: SpeechRecognition | null = null;

/**
 * Check if the Web Speech API is supported in the current browser.
 */
export function isSupported(): boolean {
  return !!(
    window.SpeechRecognition ||
    (window as unknown as { webkitSpeechRecognition: unknown }).webkitSpeechRecognition
  );
}

/**
 * Start transcription using the Web Speech API.
 * Calls `onResult` with partial and final transcription results.
 * Calls `onError` if the recognition encounters an error or times out.
 *
 * @param onResult - callback receiving (transcript, isFinal)
 * @param onError - callback receiving an error message string
 */
export function startTranscription(onResult: OnResultCallback, onError: OnErrorCallback): void {
  if (!isSupported()) {
    onError('Speech recognition is not supported in this browser. Please use Chrome or Edge.');
    return;
  }

  // Stop any existing recognition
  stopTranscription();

  const SpeechRecognitionClass =
    window.SpeechRecognition ||
    (window as unknown as { webkitSpeechRecognition: typeof SpeechRecognition })
      .webkitSpeechRecognition;

  recognition = new SpeechRecognitionClass();
  recognition.continuous = true;
  recognition.interimResults = true;
  recognition.lang = 'en-US';

  // Connection timeout — if no speech detected within 5s, error out
  const connectionTimeout = setTimeout(() => {
    if (recognition) {
      recognition.abort();
      recognition = null;
      onError('Connection timed out. No speech detected within 5 seconds.');
    }
  }, 5000);

  let hasReceivedResult = false;

  recognition.onresult = (event: SpeechRecognitionEvent) => {
    // Clear the connection timeout once we start getting results
    if (!hasReceivedResult) {
      hasReceivedResult = true;
      clearTimeout(connectionTimeout);
    }

    let interimTranscript = '';
    let finalTranscript = '';

    for (let i = event.resultIndex; i < event.results.length; i++) {
      const result = event.results[i];
      if (result.isFinal) {
        finalTranscript += result[0].transcript;
      } else {
        interimTranscript += result[0].transcript;
      }
    }

    if (finalTranscript) {
      onResult(finalTranscript.trim(), true);
    } else if (interimTranscript) {
      onResult(interimTranscript.trim(), false);
    }
  };

  recognition.onerror = (event: SpeechRecognitionErrorEvent) => {
    clearTimeout(connectionTimeout);
    const errorMessages: Record<string, string> = {
      'no-speech': 'No speech detected. Please try again.',
      'audio-capture': 'Microphone not available. Please check your permissions.',
      'not-allowed': 'Microphone permission denied. Please allow microphone access.',
      network: 'Network error. Please check your connection.',
      aborted: 'Recognition was aborted.',
    };

    const message = errorMessages[event.error] || `Speech recognition error: ${event.error}`;
    onError(message);
    recognition = null;
  };

  recognition.onend = () => {
    clearTimeout(connectionTimeout);
    // Recognition ended naturally (not from stopTranscription)
    recognition = null;
  };

  try {
    recognition.start();
  } catch {
    clearTimeout(connectionTimeout);
    onError('Failed to start speech recognition. Please try again.');
    recognition = null;
  }
}

/**
 * Stop the current transcription session.
 */
export function stopTranscription(): void {
  if (recognition) {
    try {
      recognition.stop();
    } catch {
      // Already stopped — ignore
    }
    recognition = null;
  }
}
