import axios from 'axios'

const api = axios.create({ baseURL: '/api' })

export const getOrg = () => api.get('/org')
export const getRepos = () => api.get('/repos')
export const getContributors = () => api.get('/contributors')
export const getActivity = () => api.get('/activity')
export const getCommitActivity = () => api.get('/commit-activity')

export const refreshOrg = () => api.post('/org/refresh')
export const refreshRepos = () => api.post('/repos/refresh')
export const refreshContributors = () => api.post('/contributors/refresh')
export const refreshActivity = () => api.post('/activity/refresh')
export const refreshCommitActivity = () => api.post('/commit-activity/refresh')
