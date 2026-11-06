import { inject } from '@angular/core';
import { HttpErrorResponse, HttpInterceptorFn } from '@angular/common/http';
import { MessageService } from 'primeng/api';
import { catchError, throwError } from 'rxjs';

export const globalErrorInterceptor: HttpInterceptorFn = (req, next) => {
  const messageService = inject(MessageService);
  return next(req).pipe(
    catchError((error: HttpErrorResponse) => {
      let detail = 'Unexpected error.';
      if (error.status === 0) {
        detail = 'Backend not reachable.';
      } else if (error.status >= 500) {
        detail = 'Server error. Please try again.';
      } else if (error.error?.detail) {
        detail = String(error.error.detail);
      }
      messageService.add({
        severity: 'error',
        summary: 'Request failed',
        detail,
      });
      return throwError(() => error);
    })
  );
};
