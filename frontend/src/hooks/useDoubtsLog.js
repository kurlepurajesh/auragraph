import { useState } from 'react';
import { loadDoubts } from '../components/utils';

/**
 * Manages the doubts/Q&A log for a notebook session.
 * Initialises from localStorage and exposes setter for updates.
 *
 * @param {string} id - Notebook ID
 */
export function useDoubtsLog(id) {
    const [doubtsLog, setDoubtsLog] = useState(() => loadDoubts(id));

    return { doubtsLog, setDoubtsLog };
}
