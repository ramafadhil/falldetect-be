<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Model;

class Device extends Model
{
    protected $fillable = [
        'user_id', 'name', 'location', 'source_type', 'rtsp_url', 'status',
    ];

    public function incidentAlerts()
    {
        return $this->hasMany(IncidentAlert::class);
    }
}
