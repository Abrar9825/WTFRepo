// Splash screen fade out and show main content
window.addEventListener('load', () => {
    const splash = document.getElementById('splash');
    const main = document.getElementById('mainContent');
    setTimeout(() => {
        splash.style.opacity = '0';
        splash.style.visibility = 'hidden';
        main.style.opacity = '1';
        main.style.transition = 'opacity 0.8s ease';
        main.removeAttribute('aria-hidden');
    }, 2800);
});