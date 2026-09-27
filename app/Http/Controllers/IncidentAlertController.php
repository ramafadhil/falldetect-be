<?php

namespace App\Http\Controllers;

use App\Models\Device;
use App\Models\IncidentAlert;
use Illuminate\Http\Request;

class IncidentAlertController extends Controller
{
    /**
     * Dipanggil oleh realtime_fall_detection.py setiap kali fall terdeteksi.
     */
    public function store(Request $request)
    {
        $validated = $request->validate([
            'status' => 'required|string',
            'timestamp' => 'required|date',
            'confidence' => 'required|numeric|min:0|max:1',
            'thumbnail' => 'nullable|image|max:5120', // max 5MB
            'device_id' => 'nullable|integer',
        ]);

        // Untuk tahap awal (belum ada login/auth device), pakai device pertama
        // yang terdaftar kalau device_id tidak dikirim.
        $deviceId = $validated['device_id'] ?? Device::query()->value('id');

        if (!$deviceId) {
            return response()->json([
                'message' => 'Belum ada device terdaftar. Buat 1 device dulu lewat tinker/seeder.',
            ], 422);
        }

        $thumbnailPath = null;
        if ($request->hasFile('thumbnail')) {
            $thumbnailPath = $request->file('thumbnail')->store('alerts', 'public');
        }

        $alert = IncidentAlert::create([
            'device_id' => $deviceId,
            'status' => $validated['status'],
            'confidence' => $validated['confidence'],
            'event_timestamp' => $validated['timestamp'],
            'thumbnail_path' => $thumbnailPath,
        ]);

        return response()->json($alert, 201);
    }

    /**
     * Dipanggil oleh dashboard React untuk menampilkan daftar alert terbaru.
     */
    public function index()
    {
        $alerts = IncidentAlert::with('device')
            ->orderByDesc('event_timestamp')
            ->limit(50)
            ->get()
            ->map(function ($alert) {
                return [
                    'id' => $alert->id,
                    'device_name' => $alert->device->name ?? '-',
                    'status' => $alert->status,
                    'confidence' => $alert->confidence,
                    'event_timestamp' => $alert->event_timestamp,
                    'thumbnail_url' => $alert->thumbnail_path
                        ? asset('storage/' . $alert->thumbnail_path)
                        : null,
                    'is_confirmed' => $alert->is_confirmed,
                ];
            });

        return response()->json($alerts);
    }
}
