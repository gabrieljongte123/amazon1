import { useEffect, useCallback, useRef } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { useSession } from '../hooks/useSession';
import { useChat } from '../hooks/useChat';
import { useVoice } from '../hooks/useVoice';
import ChatThread from '../components/ChatThread';
import TextInput from '../components/TextInput';
import VoiceButton from '../components/VoiceButton';
import './ChatPage.css';

function ChatPage() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const category = searchParams.get('category') || undefined;
  const initialQuery = searchParams.get('query') || undefined;

  const { sessionId, isLoading: isSessionLoading, error: sessionError, createSession } =
    useSession({ category });

  const { messages, isLoading: isChatLoading, error: chatError, sendMessage, addAgentMessage } =
    useChat(sessionId);

  const {
    isRecording,
    startRecording,
    stopRecording,
    transcript,
    error: voiceError,
    supported: voiceSupported,
  } = useVoice();

  const hasInitializedRef = useRef(false);

  // Initialize session on mount
  useEffect(() => {
    if (hasInitializedRef.current) return;
    hasInitializedRef.current = true;

    const init = async () => {
      await createSession();
    };
    init();
  }, [createSession]);

  // Add welcome message once session is created
  const hasWelcomedRef = useRef(false);
  useEffect(() => {
    if (sessionId && !hasWelcomedRef.current) {
      hasWelcomedRef.current = true;
      const welcomeText = category
        ? `Hi! I'm here to help you find exactly what you need in ${category}. What are you looking for?`
        : "Hi! I'm here to help you find exactly what you need. What are you looking for today?";
      addAgentMessage(welcomeText);

      // Auto-send initial query if provided (e.g., from "Buy Again" on homepage)
      if (initialQuery) {
        setTimeout(() => sendMessage(initialQuery), 500);
      }
    }
  }, [sessionId, category, initialQuery, addAgentMessage, sendMessage]);

  // Send transcribed text as a message when recording stops and we have a transcript
  const prevRecordingRef = useRef(false);
  useEffect(() => {
    // Detect transition from recording → idle with a non-empty transcript
    if (prevRecordingRef.current && !isRecording && transcript.trim()) {
      sendMessage(transcript.trim());
    }
    prevRecordingRef.current = isRecording;
  }, [isRecording, transcript, sendMessage]);

  // Handle option button clicks - sends the option text as a message
  const handleOptionClick = useCallback(
    (option: string) => {
      if (!isChatLoading) {
        sendMessage(option);
      }
    },
    [sendMessage, isChatLoading],
  );

  // Toggle voice recording
  const handleVoiceToggle = useCallback(() => {
    if (isRecording) {
      stopRecording();
    } else {
      startRecording();
    }
  }, [isRecording, startRecording, stopRecording]);

  const isLoading = isSessionLoading || isChatLoading;
  const displayError = sessionError || chatError || voiceError;

  return (
    <div className="chat-page">
      {/* Back button */}
      <button className="chat-page__back-btn" onClick={() => navigate('/')} title="Back to Home">
        ← Home
      </button>

      {/* Animated shopping background - full viewport coverage */}
      <div className="chat-page__bg-icons" aria-hidden="true">
        <span className="bg-icon bg-icon--1">🛒</span>
        <span className="bg-icon bg-icon--2">🛍️</span>
        <span className="bg-icon bg-icon--3">📦</span>
        <span className="bg-icon bg-icon--4">💳</span>
        <span className="bg-icon bg-icon--5">🎁</span>
        <span className="bg-icon bg-icon--6">⭐</span>
        <span className="bg-icon bg-icon--7">🏷️</span>
        <span className="bg-icon bg-icon--8">💰</span>
        <span className="bg-icon bg-icon--9">🔖</span>
        <span className="bg-icon bg-icon--10">📱</span>
        <span className="bg-icon bg-icon--11">👟</span>
        <span className="bg-icon bg-icon--12">🧴</span>
      </div>

      {isSessionLoading && (
        <div className="chat-page__status">
          <span className="chat-page__status-text">Connecting...</span>
        </div>
      )}

      {sessionError && (
        <div className="chat-page__status chat-page__status--error" role="alert">
          <span className="chat-page__status-text">{sessionError}</span>
          <button className="chat-page__retry-btn" onClick={() => createSession()}>
            Retry
          </button>
        </div>
      )}

      <ChatThread
        messages={messages}
        isLoading={isChatLoading}
        onOptionClick={handleOptionClick}
      />

      <div className="chat-page__input-area">
        <TextInput
          onSend={sendMessage}
          isLoading={isLoading}
          error={!sessionError ? displayError : null}
        />
        {voiceSupported && (
          <div className="chat-page__voice-wrapper">
            <VoiceButton
              isRecording={isRecording}
              onClick={handleVoiceToggle}
              disabled={isLoading && !isRecording}
            />
            {isRecording && transcript && (
              <span className="chat-page__voice-transcript">{transcript}</span>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export default ChatPage;
