export function setupTrailer(video, button, environment = window, documentRef = document) {
  if (!video || !button) return;
  const preference = environment.matchMedia('(prefers-reduced-motion: reduce)');
  let userPaused = false;
  let userStarted = false;
  const reflect = () => {
    const playing = !video.paused;
    button.setAttribute('aria-pressed', String(playing));
    button.setAttribute('aria-label', playing ? 'Pause trailer' : 'Play trailer');
    const label = button.querySelector?.('[data-button-label]') || button;
    label.textContent = playing ? 'Pause trailer' : 'Play trailer';
  };
  const play = () => {
    video.muted = true;
    video.play().catch(reflect);
  };
  const automatic = () => {
    video.autoplay = !preference.matches;
    if (preference.matches) {
      video.removeAttribute('autoplay');
      video.pause();
      if (!userStarted) video.load();
    } else if (!userPaused && !documentRef.hidden) play();
    reflect();
  };
  video.addEventListener('play', reflect);
  video.addEventListener('pause', reflect);
  video.addEventListener('error', reflect);
  button.addEventListener('click', () => {
    if (video.paused) { userPaused = false; userStarted = true; play(); }
    else { userPaused = true; video.pause(); }
  });
  documentRef.addEventListener('visibilitychange', () => {
    if (documentRef.hidden) video.pause();
    else if (!preference.matches && !userPaused) play();
  });
  preference.addEventListener('change', automatic);
  automatic();
}

// The GIF fallback swaps to its still poster when paused, including reduced motion.
export function setupGifTrailer(container, button, environment = window, doc = document) {
  if (!container || !button) return;
  const preference = environment.matchMedia('(prefers-reduced-motion: reduce)');
  const poster = container.querySelector('[data-poster]');
  const animation = container.querySelector('[data-animation]');
  let userPaused = false;
  const show = playing => {
    if (playing) animation.src = animation.dataset.src;
    else animation.removeAttribute('src');
    animation.hidden = !playing;
    poster.hidden = playing;
    button.setAttribute('aria-pressed', String(playing));
    button.setAttribute('aria-label', playing ? 'Pause trailer' : 'Play trailer');
    button.querySelector('[data-button-label]').textContent = playing ? 'Pause trailer' : 'Play trailer';
  };
  button.addEventListener('click', () => { userPaused = button.getAttribute('aria-pressed') === 'true'; show(!userPaused); });
  preference.addEventListener('change', () => show(!preference.matches && !userPaused && !doc.hidden));
  doc.addEventListener('visibilitychange', () => show(!doc.hidden && !preference.matches && !userPaused));
  show(!preference.matches && !doc.hidden);
}
