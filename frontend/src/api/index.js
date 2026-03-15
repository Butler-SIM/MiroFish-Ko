import axios from 'axios'

// axios 인스턴스 생성
const service = axios.create({
  // Same-origin by default so local dev can use the Vite proxy and production can
  // serve both SPA and API from a single Railway service.
  baseURL: import.meta.env.VITE_API_BASE_URL || '',
  timeout: 300000, // 5분 타임아웃(온톨로지 생성은 시간이 오래 걸릴 수 있음)
  headers: {
    'Content-Type': 'application/json'
  }
})

// 요청 인터셉터
service.interceptors.request.use(
  config => {
    return config
  },
  error => {
    console.error('Request error:', error)
    return Promise.reject(error)
  }
)

// 응답 인터셉터(오류 내성/재시도 대응)
service.interceptors.response.use(
  response => {
    const res = response.data
    
    // `success`가 false인 경우 오류로 처리
    if (!res.success && res.success !== undefined) {
      console.error('API Error:', res.error || res.message || 'Unknown error')
      return Promise.reject(new Error(res.error || res.message || 'Error'))
    }
    
    return res
  },
  error => {
    console.error('Response error:', error)
    
    // 타임아웃 처리
    if (error.code === 'ECONNABORTED' && error.message.includes('timeout')) {
      console.error('Request timeout')
    }
    
    // 네트워크 오류 처리
    if (error.message === 'Network Error') {
      console.error('Network error - please check your connection')
    }
    
    return Promise.reject(error)
  }
)

// 재시도 가능한 요청 함수
export const requestWithRetry = async (requestFn, maxRetries = 3, delay = 1000) => {
  for (let i = 0; i < maxRetries; i++) {
    try {
      return await requestFn()
    } catch (error) {
      if (i === maxRetries - 1) throw error
      
      console.warn(`Request failed, retrying (${i + 1}/${maxRetries})...`)
      await new Promise(resolve => setTimeout(resolve, delay * Math.pow(2, i)))
    }
  }
}

export default service
