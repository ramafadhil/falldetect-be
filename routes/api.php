<?php

use App\Http\Controllers\IncidentAlertController;
use Illuminate\Support\Facades\Route;

// Dipanggil oleh realtime_fall_detection.py (Python)
Route::post('/incident-alerts', [IncidentAlertController::class, 'store']);

// Dipanggil oleh dashboard React
Route::get('/incident-alerts', [IncidentAlertController::class, 'index']);