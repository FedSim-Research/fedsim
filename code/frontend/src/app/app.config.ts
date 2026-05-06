import { ApplicationConfig, provideBrowserGlobalErrorListeners } from '@angular/core';
import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { provideRouter } from '@angular/router';
import { routes } from './app.routes';
import { providePrimeNG } from 'primeng/config';
import { ConfirmationService, MessageService } from 'primeng/api';
import Aura from '@primeuix/themes/aura';
import { globalErrorInterceptor } from './interceptors/global-error.interceptor';

export const appConfig: ApplicationConfig = {
  providers: [
    provideBrowserGlobalErrorListeners(),
    provideHttpClient(withInterceptors([globalErrorInterceptor])),
    provideRouter(routes),
    ConfirmationService,
    MessageService,
    providePrimeNG({
      theme: {
        preset: Aura,
      },
    }),
  ],
};
