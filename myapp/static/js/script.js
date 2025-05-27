// Splash screen fade out and show main content
window.addEventListener('load', () => {
    const splash = document.getElementById('splash');
    const main = document.getElementById('mainContent');

    // Set initial transition for main content before changing opacity
    main.style.transition = 'opacity 0.8s ease';

    setTimeout(() => {
        // Fade out splash
        splash.style.opacity = '0';
        splash.style.visibility = 'hidden';

        // Fade in main content
        main.style.opacity = '1';
        main.removeAttribute('aria-hidden');
    }, 2800);
});
