import { useState, useCallback } from 'react';

/**
 * Manages the right sidebar's open/close state and drag-to-resize behaviour.
 */
export function useSidebar() {
    const [sidebarOpen, setSidebarOpen] = useState(true);
    const [sidebarWidth, setSidebarWidth] = useState(310);

    const startResizeSidebar = useCallback((e) => {
        e.preventDefault();
        const startX = e.clientX;
        const startW = sidebarWidth;
        const handle = e.currentTarget;
        handle.classList.add('dragging');
        document.body.style.cursor = 'col-resize';
        document.body.style.userSelect = 'none';

        const onMove = (ev) => {
            const delta = startX - ev.clientX;
            setSidebarWidth(Math.max(220, Math.min(640, startW + delta)));
        };
        const onUp = () => {
            handle.classList.remove('dragging');
            document.body.style.cursor = '';
            document.body.style.userSelect = '';
            window.removeEventListener('mousemove', onMove);
            window.removeEventListener('mouseup', onUp);
        };
        window.addEventListener('mousemove', onMove);
        window.addEventListener('mouseup', onUp);
    }, [sidebarWidth]);

    return { sidebarOpen, setSidebarOpen, sidebarWidth, setSidebarWidth, startResizeSidebar };
}
