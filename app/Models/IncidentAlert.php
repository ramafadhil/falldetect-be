<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Model;

class IncidentAlert extends Model
{
    protected $fillable = [
        'device_id', 'status', 'confidence', 'event_timestamp',
        'thumbnail_path', 'is_confirmed',
    ];

    protected $casts = [
        'event_timestamp' => 'datetime',
        'is_confirmed' => 'boolean',
    ];

    public function device()
    {
        return $this->belongsTo(Device::class);
    }
}
