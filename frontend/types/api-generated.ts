// File ini mengeksport semua tipe yang dihasilkan otomatis dari OpenAPI/Swagger
// dan menyediakan alias yang nyaman untuk digunakan di aplikasi.

// Import tipe yang dihasilkan otomatis
import type * as GeneratedApi from './generated/api';

// Re-export semua tipe yang dihasilkan
export * from './generated/api';

// Mendefinisikan tipe secara manual sementara menunggu generator berfungsi dengan baik
// Setelah generator bekerja dengan baik, ganti dengan referensi ke tipe yang dihasilkan
export interface RegisterRequest {
    phone_number: string;
    full_name: string;
    blok?: string;
    kamar?: string;
    register_as_komandan?: boolean;
}

export interface AuthErrorResponse {
    error: string;
    details?: string;
}

// Tambahkan alias lain yang bermanfaat di sini
export type ApiSuccessResponse<T> = {
    success: true;
    message?: string;
    data?: T;
    meta?: any;
};

export type ApiErrorResponse = {
    success: false;
    message: string;
    errorCode?: string;
    data?: any;
};

export type ApiResponse<T = any> = ApiSuccessResponse<T> | ApiErrorResponse;
