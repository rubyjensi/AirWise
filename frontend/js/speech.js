// Bilingual Voice Synthesis (Web Speech API)
let isSpeaking = false;

export function speakAdvisory(text, lang = 'en', onEndCallback) {
  if (!('speechSynthesis' in window)) {
    alert('Speech synthesis is not supported on this browser.');
    return;
  }

  window.speechSynthesis.cancel(); // Cancel any ongoing speech

  const utterance = new SpeechSynthesisUtterance(text);
  utterance.lang = lang === 'hi' ? 'hi-IN' : 'en-IN';
  utterance.rate = 0.95; // Slightly slower, calm cadence
  utterance.pitch = 1.0;

  // Attempt to select an appropriate voice
  const voices = window.speechSynthesis.getVoices();
  if (lang === 'hi') {
    const hiVoice = voices.find(v => v.lang.includes('hi') || v.lang.includes('Hindi'));
    if (hiVoice) utterance.voice = hiVoice;
  } else {
    const inVoice = voices.find(v => v.lang === 'en-IN' || v.name.includes('India'));
    if (inVoice) utterance.voice = inVoice;
  }

  utterance.onstart = () => { isSpeaking = true; };
  utterance.onend = () => {
    isSpeaking = false;
    if (onEndCallback) onEndCallback();
  };
  utterance.onerror = () => {
    isSpeaking = false;
    if (onEndCallback) onEndCallback();
  };

  window.speechSynthesis.speak(utterance);
}

export function stopSpeech() {
  if ('speechSynthesis' in window) {
    window.speechSynthesis.cancel();
    isSpeaking = false;
  }
}
