import { configureStore, createSlice } from '@reduxjs/toolkit';

const initialState = {
    nodes: [],
    edges: [],
    user: (() => {
        try { return JSON.parse(localStorage.getItem('ag_user')); } catch { return null; }
    })(),
};

const graphSlice = createSlice({
    name: 'graph',
    initialState,
    reducers: {
        setGraphData(state, action) {
            state.nodes = action.payload.nodes;
            state.edges = action.payload.edges;
        },
        updateNodeStatus(state, action) {
            const { id, label, status } = action.payload;
            const node = state.nodes.find(n => n.id === id || n.label === label);
            if (node) node.status = status;
        },
        setUser(state, action) {
            state.user = action.payload;
        },
    }
});

export const { setGraphData, updateNodeStatus, setUser } = graphSlice.actions;

export const store = configureStore({
    reducer: { graph: graphSlice.reducer }
});
