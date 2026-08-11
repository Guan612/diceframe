import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'
import { i18n } from './i18n'
import './styles/tokens.css'
import './styles.css'
import './styles/v2.css'

const app = createApp(App).use(createPinia()).use(router).use(i18n)

// Hash history resolves asynchronously on a direct deep link. Mounting before
// that point briefly treats /join and player /play links as owner routes and
// fires authenticated startup requests that can only return 401.
void router.isReady().then(() => app.mount('#app'))
