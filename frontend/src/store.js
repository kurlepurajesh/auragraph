import { configureStore, createSlice } from '@reduxjs/toolkit';

const initialState = {
  user: (() => {
    try { return JSON.parse(localStorage.getItem('ag_user')); } catch { return null; }
  })(),
};

const appSlice = createSlice({
  name: 'app',
  initialState,
  reducers: {
    setUser(state, action) {
      state.user = action.payload;
    },
  }
});

export const { setUser } = appSlice.actions;

export const store = configureStore({
  reducer: { app: appSlice.reducer }
});
