<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::create('incident_alerts', function (Blueprint $table) {
            $table->id();
            $table->foreignId('device_id')->constrained('devices')->cascadeOnDelete();
            $table->string('status')->default('fall_detected');
            $table->decimal('confidence', 4, 3);
            $table->dateTime('event_timestamp');
            $table->string('thumbnail_path')->nullable();
            $table->boolean('is_confirmed')->nullable();
            $table->timestamps();

            $table->index(['device_id', 'event_timestamp']);
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('incident_alerts');
    }
};
