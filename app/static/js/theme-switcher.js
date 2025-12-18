// A self-invoking function to avoid polluting the global scope
(() => {
    const htmlElement = document.documentElement;
    const switcher = document.getElementById('theme-switcher');
    const lightIcon = switcher?.querySelector('.light-icon');
    const darkIcon = switcher?.querySelector('.dark-icon');

    // Function to set the theme
    const setTheme = (theme) => {
        htmlElement.setAttribute('data-theme', theme);
        localStorage.setItem('theme', theme); // Save preference

        // Update icon visibility
        if (lightIcon && darkIcon) {
            if (theme === 'dark') {
                lightIcon.style.display = 'none';
                darkIcon.style.display = 'inline-block';
            } else {
                lightIcon.style.display = 'inline-block';
                darkIcon.style.display = 'none';
            }
        }
        
        // [IMPORTANT] Dispatch a custom event for other scripts to listen to
        // This is crucial for things like charts to update their colors
        document.dispatchEvent(new CustomEvent('themeChanged', { detail: { theme } }));
    };

    // Event listener for the button
    switcher?.addEventListener('click', () => {
        const currentTheme = htmlElement.getAttribute('data-theme');
        const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
        setTheme(newTheme);
    });

    // Initial theme setup on page load
    // 1. Check for saved theme in localStorage
    // 2. If not found, check for OS preference
    // 3. Default to light if nothing is set
    const savedTheme = localStorage.getItem('theme');
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    const initialTheme = savedTheme || (prefersDark ? 'dark' : 'light');
    
    setTheme(initialTheme);
    lucide.createIcons(); // Re-render icons after DOM manipulation
})();